# MKT-D01 — Real-Time Fast Lane (earnings / breaking instant publish)

**Department:** Engine Room (growth_os) + Broadcast (distribution) · **Priority: P0** · **Status: W0 SHIPPED (PR #3053, 2026-07-19) — provider seam + tick body + daemon w/ kill-switch + quarantine ledger; W1 (always-on host + paid feed key) awaits operator**
**Architecture doc (read it):** `research/MARKETING_REALTIME_FASTLANE_ARCHITECTURE_BY_FABLE.md`
**Operator directive (verbatim intent):** "earnings comes out usually before market opens and after market closes… immediate events… cannot be a scheduled post." Publish within **seconds-to-minutes** of the event, not on the nightly clock.

## Why

The nightly pipeline is a scheduled batch (~67 min render on a Mac Studio). Earnings, halts, and breaking macro events are *immediate* — the reach window on X is the first minutes. TrendSpider's highest-reach posts are instant earnings reactions. This docket builds the event-driven lane that runs **outside** the nightly, produces a finished post (card + copy) into an outbox, and hands it to the D02 actuator.

## What already exists (do not rebuild)

- `engine/marketing/earnings_card.py` — `render_earnings_card` (BEAT/MISS chips, company logo). #3003.
- `engine/marketing/chart_render.py` — `render_chart_v2`, `load_ohlcv`, `resolve_logo`; CTA footer branding.
- `engine/marketing/logo_cache.py` — favicon logomark fetch/cache.
- `engine/marketing/copywriter.py` — `validate_copy`, personas, `write_posts_deterministic` (+ LLM lane, #3032).
- Phase-A (scheduled next-morning earnings recap) concepts in the architecture doc.

## Deliverables

### W0 — daemon scaffold + provider seam (buildable today, no operator input)
1. `engine/marketing/earnings_feed.py` — pluggable provider seam: `fetch_events(since) -> [ {ticker, when, eps_actual, eps_est, rev_actual, rev_est, source} ]`. Ship a **free poll provider first** (public earnings-wire scrape/RSS lane with polite rate limits); leave a stub for a paid low-latency provider keyed off env (`EARNINGS_API_KEY`).
2. `engine/marketing/fastlane.py` — the loop body (pure, testable): poll → dedupe against a seen-ledger (`data/marketing/fastlane_seen.jsonl`, local-only, **never committed** — intraday lanes must not advance repo ledgers) → eligibility (ticker in our stockdata universe, mcap floor, market-hours window pre/post) → render earnings card + write copy (persona: Scorekeeper/Desk; MUST pass `validate_copy`) → emit an **outbox item** (the D02 contract: `data/marketing/outbox/<id>.json` + media file).
3. `scripts/marketing_fastlane_daemon.py` — thin runner: interval loop, `--once` and `--dry-run` flags, `MARKETING_FASTLANE_ENABLED` env kill-switch, structured log lines.
4. Tests: fixture events → outbox item in one tick; restart-dedupe; ineligible tickers skipped; validate_copy rejection quarantines rather than posts.

### W1 — always-on deployment (needs operator: approve an always-on host)
5. launchd plist for the Mac Studio (pattern + lethal traps live in memory `mm-bot-launchd-reboot-survival`: TCC blocks bash job roots from ~/Documents — python3 root holds the grant; launchd PATH lacks CLIs). Heartbeat file + `::warning` if stale >15 min during market windows.
6. Latency upgrade: swap the free poll provider for a paid low-latency feed once the operator provisions a key (env only, never repo).

### W2 — beyond earnings
7. Accept `breaking` events from D05 (breaking desks) through the same outbox path; halts/circuit-breakers if a free source proves reliable.

## Acceptance

- Simulated earnings drop → outbox item (card PNG/SVG + validated copy + provenance) in **<60 s** of the poll tick; dedupe survives restart; zero git writes from the daemon; kill-switch verified.
- Nightly render budget untouched (the daemon is fully off the render path).

## Traps

- **Ledger law:** nightly is the sole advancer of forward ledgers; the daemon writes only its local seen-ledger + outbox, never `git add`.
- Free-source scrapes: classify response TEXT strictly — ok-looking results can carry error banners (memory `mm-bot-key-rotation`).
- Copy with numbers: EPS/revenue figures must be in the `numbers_whitelist` fed to `validate_copy` or the post gets rejected.
