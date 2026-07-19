# MKT-D06 — Radar W1: Real Opportunity Feeds + Cashtag Traffic Tiers

**Department:** Radar (intelligence) · **Priority: P2** · **Status: ready now**
**Charter:** `engine/marketing/departments.py` id=`intelligence` ("Market, Audience & Opportunity Intelligence", wave 1, 10 chartered engines — stubs).

## Why

The CMO loop reads an opportunity queue (`engine/marketing/opportunity_bus.py`, ~121 lines) that is currently seeded/static. Radar's job is to make it real: continuously discover *what we could be posting about that we aren't*, and *which cashtags carry traffic*, so the Content Studio and Movers Desk aim at live attention instead of a fixed universe.

## What already exists (do not rebuild)

- `opportunity_bus.py` scoring/queue shape — extend its feed side, keep its consumer contract.
- Movers Desk (#3020) consumes theme lists — Radar's traffic tiers should *feed* it, not duplicate it.
- The TrendSpider corpus + intelligence docs: `research/TRENDSPIDER_GROWTH_SEO_AND_GUERRILLA_MARKETING_INTELLIGENCE_FOR_FABLE.md` (competitor posture baseline).

## Deliverables — W1

1. **Internal signal-surplus scan** (`engine/marketing/radar_internal.py`): sweep the repo's own artifacts (Prophet slate, confluence `active_now`, stage-analysis boards, movers, earnings calendar) and diff against what the last N content plans actually posted → "unposted postable assets" queue with staleness. Pure artifact reads, no new computation.
2. **Cashtag traffic-tier table** (`data/marketing/cashtag_tiers.json`, nightly, cached): tier tickers by expected X attention using deterministic proxies we already have — dollar volume, |%move|, earnings proximity, index membership. Tiers: T1 (megacap/meme, always liquid attention), T2 (active this week), T3 (dead). Movers Desk + Content Studio consume tiers to pick cashtags; D03 Lab later replaces proxies with measured reach.
3. **Competitor cadence watch (W1 = manual-corpus baseline):** a small structured file distilled from the TrendSpider corpus (formats, posting times, thread patterns) that the Studio can consult; a live scrape lane is W2 and needs its own red-team pass.
4. Admin **Radar page** enrichment (via `designer`): the opportunity queue with age/score, the tier table, and "what we're NOT posting" — the legibility the operator asked for ("looks completely autonomous, can't see internals").
5. Tests: surplus scan finds a seeded unposted asset; tier math on fixtures; queue consumer contract unchanged (CMO loop still reads it).

## Acceptance

- Nightly produces `cashtag_tiers.json` + a populated opportunity queue with ≥3 real feed sources; admin Radar page renders both; Movers Desk picks cashtags using tiers (one-line integration, behind a config flag until verified).

## Traps

- Radar **observes and scores; it never posts** — everything routes through Content Studio/outbox + Sentinel.
- Keep the sweep cheap (artifact reads only) — this runs nightly inside the render budget.
- Don't re-derive what Movers Desk already computes (top movers, theme membership); Radar adds the *attention* dimension, not the *movement* dimension.
