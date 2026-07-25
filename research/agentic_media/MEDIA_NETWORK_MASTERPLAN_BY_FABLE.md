# Media Network — automated publication estate (masterplan, docket D14)

**Program:** Agentic Media / Media Network · **Author:** Fable · **Date:** 2026-07-25 (rev 2 after adversarial review) · **Status:** CHARTERED
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` (AM-R1 provenance, AM-R4 transformation — rev 2 corrected premise, AM-R7 measurement, AM-R9 monetization)
**Extends:** the D12 free estate (`scripts/build_free_content.py`, `content/seo/blog/*.md`, `templates/seo_article.html.j2`, `/blog/` already in `app/regwall.py` PUBLIC_PREFIXES + all Caddy matchers); Beacon SEO Director (`engine/marketing/seo_director.py`, weekly 0–100 audit); Search Console ingestion adapter (#3160 — currently dark, needs the operator's GSC service-account credential); Research Vault (`data/research_vault/catalog.json`); Chronicle packs (sibling masterplan).

Goal: turn the 6-post hand-written blog into an **automated daily publication** that earns search traffic, backlinks, owned audience, and subscription leads — then, only when earned, additional genuinely distinct publications. The operator's Zerohedge observation is adopted as design: one strong publication per brand, one primary X account per publication, aggregation done *with* attribution rather than masked.

## §0 ACCEPTANCE GATES

**Ledger law (all waves):** `data/press/published.jsonl` is a press-workflow-owned receipt ledger on the sanctioned outbox precedent — the press publish workflow is its sole writer, with explicit `git add` scoping in that workflow (mirror of marketing-publish.yml's pattern); no other lane appends.

**W1 (press engine + first two desks) not done unless:**
1. 10 consecutive generated articles (mixed desks) each pass the full validator suite (§5) with zero manual edits; validator failures quarantine (regenerate max twice, then drop the slot — a thin day beats a padded one).
2. Every aggregation piece names + links its primary source above the fold; the **≥40% our-value gate is computed, not vibes**: ≥40% of the piece's word count sits in blocks whose every number/claim resolves to a first-party ref (engine artifact, chronicle event with `source` in our own artifacts, or vault summary), computed by the fact-anchor resolver and printed in the `validator_report` stored in `data/press/published.jsonl`.
3. Every article carries the byline/AI-disclosure block + standing not-investment-advice footer; `/blog/editorial-policy.html` ships in the same wave.
4. Frontmatter exactly matches the existing contract (`family: article` for all three desks; `slug` == filename stem, no date prefix — dedupe lives in the published ledger, not the filename; required keys slug/family/title/description/published/updated per `scripts/build_free_content.py:_validate`), and the §5 suite pre-checks title/description lengths so drafts fail inside the press lane, not at the site builder.
5. `python -m scripts.build_free_content --check` is green AND **newly wired into CI** (paths-filtered on `content/seo/**` + the seo templates) — it is currently a manual command; W1 makes the drift law enforceable.
6. Posts render on `/blog/` with correct JSON-LD Article and RSS updated by the builder. **Sitemap ownership stated and honored:** the free-content builder does NOT write `sitemap.xml` — entries land on the next nightly render's core-sitemap pass; the press lane commits `content/seo/blog/` + `site/blog/` only (never `site/sitemap.xml`), accepting the indexing lag, and one press URL is verified present in `site/sitemap.xml` after the next nightly completes (end-to-end, once).
7. Zero regwall/Caddy edits needed (staying under `/blog/`).
8. Generation runs off the render path in a **new publish workflow modelled on `marketing-publish.yml`** (none exists for the free estate today — the current 6 posts are hand-run) with an explicit per-day token budget + circuit breaker; a kill switch (`PRESS_PUBLISH_ENABLED` repo variable, same pattern as the marketing publisher's #3361 switch) dark-ships the whole lane.
9. **Research Desk preconditions:** the operator has acknowledged the standing MarketDesk licensing flag (umbrella §8) for public commentary use; and the vault SEO landing pages (`/research/<slug>.html`) are verified **committed + live** before any piece links them — recon found they have never actually been committed (silent-swallow in `scripts/build_research_vault.py` ~L233-236; fix chipped separately). Until live, Research Desk pieces link `/research_vault.html` instead.

**W2 (cadence + measurement) not done unless:** 2 weeks at target cadence with zero validator overrides; the operator has provisioned the GSC service-account credential and Search Console rows flow per URL into the D12 adapter store; Beacon weekly score not degraded vs pre-launch baseline; per-desk scorecards (sessions, impressions, CTR, email captures, D07-tagged trial attributions) rendering in admin.

**Any spin-out publication (W4+) not done unless:** its §7 earn-gates are met AND operator ratifies name/brand/domain AND its masthead carries "A Mastermind Media publication" + AI-disclosure policy page AND regwall/Caddy dual-mirror is edited for any new prefix (`app/regwall.py:60` PUBLIC_PREFIXES + the Caddyfile not-path matcher lists) — never silently behind the regwall.

## 1. The three desks (start with two, add the third when Chronicle W1 lands)

| Desk | Content | Source spine | Cadence target | The honest wedge |
|---|---|---|---|---|
| **The Brief** (aggregation, attributed) | 300–600w: what happened, why it matters, what to watch — on the day's 3–5 most attention-worthy market stories | breaking/news desks + movers + chronicle short pack + our engine stats | 2–3/day (W1: 1–2) | speed + our-data receipts; every piece links its sources prominently (Techmeme/Axios idiom, AM-R4) |
| **Research Desk** (institutional coverage) | "What the street is telling clients": single-report **commentary** + weekly cross-report synthesis ("5 banks on positioning this week"), stance map by institution — facts re-stated in our words + ≤2 short attributed quotes; never wholesale summary republication (AM-R4 rev 2: the vault estate is regwalled, and the licensing flag is open) | vault catalog `summary_points` + chronicle medium pack | 1/day + 1 weekly synthesis | **nobody else automates this because nobody else has the vault**; links the vault (→ Pro funnel) — `/research/<slug>.html` once live, `/research_vault.html` until then |
| **Editorial** (original thesis) | 900–1,500w pieces: named theses with mechanism, falsifier, and scheduled review; monthly "state of the story" epoch pieces | chronicle medium/long packs + engine surfaces; best pieces promoted to site Research Reports **behind a non-LLM-origination check** | 2–3/week | receipts-culture longform; the only desk allowed a strong voice, and it grades itself in public |

**Editorial thesis-provenance contract (mirror of Persona §4, LLM-origination law):** every named thesis in an Editorial piece carries a `seed_ref` to a calibrated engine/signal surface or a Chronicle narrative id; the LLM writes mechanism/prose/falsifier language *around* the seeded call and may de-escalate, never originate or strengthen it. The §5 validator hard-fails a draft whose thesis has no seed reference. Promotion into site Research Reports is an authority move and passes the same check plus main-loop review.

Explicitly **not** built (DNR via AM-R1/AM-R4): a Zerohedge-rewrite lane that paraphrases third-party articles wholesale ("masked original content"); scaled programmatic "is $X a buy" article farms (guerrilla doctrine §2.4 already rejects; Google scaled-content-abuse names it); any desk that publishes engine signals as advice (plain-word stance + disclosure law carries over).

## 2. Why this earns traffic (and the failure it avoids)

Search rewards what the March-2024+ policy era punishes elsewhere: original data, first-party expertise, consistent publication identity. We have original data nobody else publishes (engine stats, vault coverage, receipts). The failure mode to avoid is the 2024–26 graveyard of AI content sites: high-volume derivative text, no identity, no proof-of-work → deindexed as scaled content abuse. Every desk's design forces the differentiator into the piece structurally (§0 W1 gate 2's computed our-value metric).

## 3. Identity + disclosure

Byline: **"Mastermind Research Desk — AI-assisted, human-supervised."** A standing `/blog/editorial-policy.html` page states the pipeline honestly (automated drafting, deterministic validators, operator oversight, correction policy) — in 2026 this is a differentiator, and it is also what Google News' sponsorship/editorial-disclosure rules and our own receipts culture demand. Corrections append visibly (errata block), never silent-edit — same law as chronicle epochs.

## 4. Pipeline (`engine/press/`)

`desk_planner.py` (deterministic: pick today's stories/reports from source spines; dedupe vs `data/press/published.jsonl`) → `writer.py` (LLM per desk: prompt = desk contract + chronicle pack via the Chronicle-W2 injection helper + source facts + house style; Opus for Editorial, cheapest-passing for Brief per AM-R6) → `validators.py` (§5) → emits `content/seo/blog/<slug>.md` on the **existing frontmatter contract** (gate 4) → the existing free-content builder renders `site/blog/` + RSS (sitemap on next nightly, gate 6) → the **new press publish workflow** commits (gate 8). Ledger: `data/press/published.jsonl` (append-only: id, desk, sources[], seed_refs[], validator_report, urls — §0 ledger law).

## 5. Validator suite (the anti-slop gate, all deterministic)

**Corpus separation + precedence (so the gates don't fight):** fact-anchoring applies to **numbers and explicitly-attributed quotes** — every number/quote in the draft must appear in the supplied source facts (no originated numbers); attributed-quote spans are then **excluded** from the shingle computation. The **close-paraphrase detector** runs over the draft's *unattributed prose* against the **raw source document** (not the extracted fact strings); overlap above the declared threshold (shingle Jaccard, set in config, not raisable without an operator ruling) = hard fail.

Full suite: fact-anchor check; **thesis-provenance check** (Editorial: every named thesis carries a resolvable `seed_ref` — §1); quote-length lint (≤2 short attributed quotes per piece, AM-R4); source-attribution structure check (Brief: source link above the fold; Research: vault link present); close-paraphrase detector (as above) + 30-day self-similarity radar vs our own posts; **our-value ≥40% metric** (computed per §0 gate 2); banned-lexicon + advice-lexicon (Sentinel lists); disclosure block present; frontmatter pre-check (title/description lengths, family, slug); cheese-test voice validator (v3 port); length/structure budget per desk. Failures quarantine (max 2 regenerations, then drop the slot).

## 6. Distribution

Native-first on X: each piece becomes a value-complete post (the stat/chart/claim in-post), link in reply/card — per the reach-suppression + $0.20/link-post API reality. The flagship desk account carries Brief/Editorial shares; the Research Desk gets its own X account only at S3 of the persona ladder. Cross-account citation follows the umbrella §5.2 similarity rule (publication account + flagship may each share a piece once with distinct framing; personas cite asynchronously >24h, radar-checked). RSS ships day one (already in the builder); newsletter digest joins the D07/lifecycle lane later (owned audience).

## 7. Spin-out gates (second publication, the .co/.info/.org replacement)

A new publication (own name/brand, possibly own domain) may be chartered only when ALL hold: flagship estate ≥ threshold (e.g. 50k organic sessions/mo sustained 2 months, Search Console-verified); a desk has a coherent standalone identity (e.g. zh-language market wire; options/vol daily) whose audience demonstrably differs; operator ratifies name + budget; AM-R1 masthead disclosure. New domains start with honest zero authority — that cost is accepted consciously, for brand reasons, never for evasion (the evasion motive is DNR'd). Cap: ≤3 publications through 2026.

## 8. Monetization

Subscriptions first (Research Desk → vault Pro funnel is the designed lead path; D07 UTM attribution measures it). Ads per AM-R9's five-condition gate (Beacon floor + trailing-30-day our-value pass + density cap + operator ruling + commercial-viability floor). Affiliate/creator syndication per D11 when ratified.

## 9. Waves

| Wave | Ships | Model lane |
|---|---|---|
| **W1** | `engine/press/` planner+writer+validators, Brief + Research desks at W1 cadence, **new press publish workflow** + kill switch, published ledger, editorial-policy page, `--check` CI wiring, admin Press panel (drafts/quarantine/scorecards read-only) | Opus `builder` for engine/workflow; admin panel + any `/blog/` template change via pinned markup or `designer`; runtime generation tiers per AM-R6 (Brief cheap, Editorial opus) |
| **W2** | Cadence to target, per-desk scorecards + Search Console wiring (credential precondition), weekly ops report in admin | Opus `builder` |
| **W3** | Editorial desk (needs Chronicle W1 narratives), thesis-provenance validator live, Research Reports promotion path (main-loop reviewed), newsletter digest | Opus `builder`; promotion review in main loop |
| **W4+** | Spin-out per §7 gates; zh-language desk evaluation | Ruling-gated; publication design via `designer`/Fable per AM-R6 |

## 10. Risks (printed)

- **Cold-start**: a 6-post blog has ~zero authority; expect months of thin search traffic. The Research Desk is the differentiated wager (unique corpus) and X-native distribution carries the interim. Scorecards make "it's not working" cheap to see; kill gates per desk at 12 weeks.
- **LLM cost**: bounded by per-day budget + circuit breaker; Brief on cheap models, Opus only where the validator suite demands it.
- **Vault dependency**: Research Desk inherits vault ingestion health (hourly lane), the open MarketDesk licensing flag (operator acknowledgment is a W1 gate), and the not-yet-live `/research/` landing pages (chipped fix; interim links to `/research_vault.html`).
- **Render-lane interplay**: the press lane never touches `site/sitemap.xml` (nightly owns it) and commits only its own paths — the stale-checkout clobber class (memory: render-lane-stale-checkout-clobber) is designed around, not discovered later.
- **Google policy drift**: Beacon weekly audit is the tripwire; any manual action = immediate cadence freeze + operator escalation (runbook line in W1).
