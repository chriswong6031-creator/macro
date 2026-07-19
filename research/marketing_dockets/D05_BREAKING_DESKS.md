# MKT-D05 — Breaking Desks: News / Policy-Feed Ingestion + Cite Cards

**Department:** Radar (intelligence) + Studio · **Priority: P1** · **Status: W0 ready now; live publish depends on D01+D02**
**Operator intent:** breaking market-moving news (macro prints, policy/tariff headlines, Truth Social posts, CENTCOM-class geopolitical events) should become fast, cited, illustrated posts — the second immediate-content lane beside earnings.

## Why

Breaking reaction is a top reach format from zero followers (the event's cashtags/keywords carry the traffic, not our follower count). But it is also the top **credibility risk** lane: uncited or mis-summarized breaking content is how finance accounts die. The design is therefore: deterministic ingestion + relevance scoring, LLM used ONLY to summarize-with-citation, and a card format that shows the source.

## What already exists (do not rebuild)

- Macro/market fact engines: `engine/marketing/market_facts.py` (#3003) — the fact/numbers-whitelist pattern to copy.
- Event content type already in every account tilt (`config/marketing.yml desk_network`, kind=`event`).
- Card rendering infrastructure: `chart_render.py` (branding, CTA footer, logo cache).
- D01 outbox path for immediate publish; D08 Sentinel gate.

## Deliverables

### W0 — ingestion + relevance + card (buildable now, fixtures + polite free sources)
1. `engine/marketing/breaking_feed.py` — adapter seam with per-source pollers (RSS/JSON lanes first: major wire RSS, Fed/BLS/BEA release feeds, official-account mirrors for policy posts). Each adapter returns `{id, source, url, published_at, headline, body_snippet}`. Rate-limited, `User-Agent` honest, seen-ledger dedupe (local-only, never committed).
2. `engine/marketing/breaking_relevance.py` — **deterministic** relevance filter: keyword/entity match against our universe (tickers, sectors, macro keys), event-class taxonomy (macro_print / policy / geopolitical / company_news), a market-hours weighting, and a salience score. No LLM in the filter.
3. Summarize-cite lane (LLM, gated like the copywriter — `llm_auth` waterfall + `MARKETING_LLM_ENABLED`): ≤2-sentence summary that may ONLY restate facts present in the source snippet; carries the source name + timestamp; passes `validate_copy` with numbers whitelisted from the source text. Deterministic fallback = headline + source.
4. Breaking card renderer in `chart_render.py` style: headline, source chip + timestamp, related-ticker mini strip (price/% if in universe), brand footer. No fabricated imagery.
5. Tests: fixture feed → relevance ranks a CPI print above a celebrity headline; summary rejected when it introduces an unsourced number; card renders with source chip.

### W1 — wire to the fast lane
6. Emit qualifying items (salience ≥ threshold) as `breaking` outbox items through D01's path, Sentinel-gated (D08). Scheduled next-morning digest of sub-threshold items as a fallback `event` post in the nightly plan.

### W2 — harder sources
7. Truth-Social / X official-account monitors need scrape lanes with real ToS/fragility review — red-team memo first (opus `reviewer`), then implement only the sources that pass. Screenshot-of-source as citation imagery where APIs don't exist.

## Acceptance

- Fixture CPI-print event → cited card + validated copy in the outbox within one poll tick; the source URL is present in provenance end-to-end.
- LLM summary path provably cannot introduce numbers not in the source (test with an adversarial fixture).
- Zero repo/git writes from pollers; render budget untouched.

## Traps

- **LLM law:** the model summarizes and de-escalates only — it never decides *whether* something is market-moving (the deterministic relevance score does) and never adds interpretation ("this is bullish") in the breaking lane. Stance stays in our signal lanes where we have receipts.
- Geopolitical/tragedy events: Sentinel tone rule — factual, no CTA footer on human-tragedy items (suppress the trial pitch on those cards; a config flag on the card renderer).
- Source reliability tiers: official feeds > wires > aggregators; the card must show the tier-source actually used, not a laundered re-report.
