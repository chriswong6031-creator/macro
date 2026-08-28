---
workstream: "WS:STOCK-DOSSIER-LIVE-QUOTE"
session: "claude/stock-dossier-live-quote-p0 (worktree stock-dossier-live-quote-dae491)"
model: opus
ended_because: complete
mission: >
  Sol commission stock-dossier-live-quote-p0-20260827-sol-001: make every US
  dossier built from templates/ticker.html.j2 show the same current
  regular-session quote plane as Terminal, with "Live" permitted only when the
  quote itself proves measured current freshness, and the nightly HTML remaining
  an honest fallback rather than a fake-live value.
state_before: >
  /stocks/NVDA.html served a baked $209.66 with a static "-$3.39 · -1.59%" under
  a pulsing green "Live" chip. The measured regular-session close at the same
  moment was $227.98 (+8.74%): $209.66 was that row's own prevClose, so the page
  showed the PREVIOUS close and the PREVIOUS day's move — an inverted sign — and
  labelled it live. The chip was rendered by `{% if not stale %}` where `stale`
  derives from the BUILD's data date, so it was a claim about the render dressed
  as a claim about the market. The hero day move had no live binding at all, and
  the hero/sticky prices were .nb-px nodes owned by the shared live.js poller,
  which resolves its snapshot relative — from /stocks/ that is
  /stocks/live/quotes.json, a path that does not exist.
changed:
  - path: app/dossier_quote.py
    what: >
      NEW. GET /api/dossier-quote/{ticker}: a bounded localhost projection over
      the already-running Terminal Quote Hub. Validates the ticker BEFORE any
      upstream call, bounded timeout and bounded read, two-bucket rate limit,
      Cache-Control private/no-store, and fails closed (503) rather than
      returning a 200 carrying a plausible price. Emits an allowlisted, DEBRANDED
      payload — source/basis/anchor_source and every transport field are dropped,
      never forwarded. Freshness classification is the core: `freshness` grades
      the FEED, `session` the MARKET, and "live" requires the hub's own measured
      realtime flag AND a non-delayed basis AND the row's own clock inside the
      bound. The staleness bound is SESSION-AWARE because upstream stamps `ts`
      from the vendor print clock; a flat bound would mark every correct
      after-hours close stale and revert the page to baked.
  - path: templates/ticker.html.j2
    what: >
      Hero and sticky prices moved off the shared .nb-px selector onto .dq-px, so
      the dossier price has exactly one writer. The day move gained real bindings
      so it repaints WITH the price rather than sitting static beside it. The
      hard-coded "Live" stamp was replaced by a stamp that ships in an honest
      `baked` state naming the date of the bytes actually served, upgraded only
      by a measured quote — so the page stays truthful with JS off. Per-state CSS
      reserves the green pulsing pip for `live` alone.
  - path: site/assets/js/dossier-live-quote.js
    what: >
      NEW client. Writes price and move together from ONE quote or not at all; a
      partial paint would desynchronise them. Keeps baked values on any failure.
      Sets both language spans for every state. Names the session date outside
      regular hours, because upstream can hand back the previous session's move.
  - path: app/main.py
    what: router wiring only.
  - path: tests/test_dossier_quote_api.py + tests/test_dossier_live_quote_surface.py
    what: >
      35 tests. Server tests run against a VERBATIM capture of the production hub
      row, including the fields we deliberately drop, so the debrand and allowlist
      assertions are not self-referential.
verified:
  - >
    End-to-end against the REAL running hub over an SSH tunnel: NVDA -> 200
    {price 227.98, prev_close 209.66, change_abs 18.32, change_pct 8.7379566917867,
    freshness "delayed", session "post"}; AAPL -> 200 (proves it is not
    NVDA-specific); unknown symbol -> 404; path traversal -> 404; every response
    Cache-Control private,no-store and free of vendor strings.
  - >
    Browser, on the actually-served page: before 209.66 / "-$3.39 · -1.59%" /
    green pulsing "LIVE"; after 227.98 / "+$18.32 · +8.74%" / grey static
    "After hours · 2026-08-27". Discrimination proven both ways — a fresh
    realtime row in an open regular session DOES produce a green pulsing "Live",
    while stale / wrong-ticker / null-price payloads all leave the numbers
    untouched. 375px: no horizontal overflow. zh renders 盘后 · 2026-08-27.
    No console errors from the module.
  - >
    `python3 -m pytest tests/test_dossier_quote_api.py
    tests/test_dossier_live_quote_surface.py -q` -> 35 passed. Existing dossier
    guards (test_check_stock_dossier_integrity, test_company_intelligence_dossier_js)
    -> 52 passed. check_site_asset_refs OK; check_template_site_sync OK (94 pairs);
    check_design_system exit 0.
  - >
    Deploy path: `app/.*\.py` is inside the macro-api restart regex
    (app/deploy/update.sh:1234), and templates/ticker.html.j2 is in render.yml's
    scope whitelist (line 544 -> scope `macro`), so the API restarts and the
    dossier pages regenerate. /api/* is excluded from both the regwall and
    paywall matchers in app/deploy/Caddyfile, so the route is reachable for
    logged-out readers.
do_not_redo:
  - >
    Do NOT read the Quote Hub contract from the charting-app checkout on the
    fleet host — it is from 2026-07-13 and does not match production. A census
    run against it returned a fully-cited contract with the WRONG freshness
    semantics and no snapshot leg. Probe the running service.
  - >
    Do NOT put the dossier price back on .nb-px, and do NOT apply a flat
    staleness bound. Both are explained in the workstream's danger_areas.
  - >
    Do NOT set HUB_REALTIME_QUOTES=1 without the ruling below. It was authorized
    by the commission, is genuinely OFF, and was still deliberately not set.
danger_areas:
  - >
    `chg` from the hub is a PERCENT despite the name; the dollar move must be
    derived as last - prevClose. `ts` is the vendor print clock and freezes after
    the close. Both mis-readings ship a plausible number and raise nothing.
  - >
    extPrice/extChg are a DIFFERENT session and had the opposite sign to the
    regular session on the captured row (-0.76% vs +8.74%). Never render them as
    the day move.
  - >
    Our 120s live bound is deliberately TIGHTER than the hub's generous
    15-minute per-name realtime bound. That is a documented choice, not an
    oversight — retune it deliberately or not at all.
---

## Exact remaining gate

**One ruling, one re-verification.**

1. **HUB_REALTIME_QUOTES is a shared entitlement switch, not a freshness lever.**
   The commission authorized setting it. It is off (`snapshotFeed.realtime:
   false`, `verdict.tier: "off"`). It was not set, because it is also read by
   `terminal/app/api/intraday/route.ts` and `hub/README.md:46` states it is
   deliberately *"one lever for everything real-time-derived, so the pending
   anonymous-vs-sign-in ruling has a single switch to land on"* — flipping it
   unlocks the Terminal's 1s/5s/15s/30s bar band for users. It also requires the
   Massive "Stocks Advanced" plan, and the entitlement record is explicit that a
   per-feed vendor designation, not that record, is the authority for a feed.
   Independently, `hub/lib/snapshot.js` makes no freshness claim outside a live
   US session, so flipping it post-close would have changed nothing observable
   while costing a live-service restart that drops the Terminal's 24/7 crypto
   sockets. Needs an explicit Sol/Chairman answer on whether unlocking the
   seconds band is intended.

2. **The realtime verdict itself is natural-time-gated.** The US regular session
   was closed throughout this work, so the `live` branch is proven by
   construction, by unit test, and in a browser — but has not been observed
   against a genuinely realtime production feed. Re-verify during an open RTH.

## One adjacent instance, deliberately NOT fixed

`templates/intelligence_hub.html.j2:400` renders `<span class="live"></span>{{
t('Live', '实时') }} · <time>{{ built[:10] }}</time>` — the same class of claim
(a "Live" pip driven by the build), though weaker, since it prints the build date
beside itself. Different surface, outside the frozen P0 scope of "every US
dossier using the same template", and the commission said one PR only. Reported,
not touched.
