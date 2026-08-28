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
  - claim: >
      End-to-end against the REAL running hub: NVDA -> 200 {price 227.98,
      prev_close 209.66, change_abs 18.32, change_pct 8.7379566917867, freshness
      "delayed", session "post"}; AAPL -> 200 (not NVDA-specific); unknown symbol
      -> 404; path traversal -> 404; every response Cache-Control private,no-store
      and free of vendor strings.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'curl -s
      "http://127.0.0.1:3100/quotes?syms=NVDA"' then the route driven over an SSH
      tunnel with DOSSIER_QUOTE_HUB_URL pointed at it via fastapi TestClient
  - claim: >
      Browser, on the actually-served page: before 209.66 / "-$3.39 · -1.59%" /
      green pulsing "LIVE"; after 227.98 / "+$18.32 · +8.74%" / grey static
      "After hours · 2026-08-27". Discrimination proven both ways — a fresh
      realtime row in an open regular session DOES produce a green pulsing
      "Live", while stale / wrong-ticker / null-price payloads leave the numbers
      untouched. 375px: no horizontal overflow. zh renders 盘后 · 2026-08-27.
    command: >
      preview_start site-static (python3 -m http.server 8931 --directory site);
      navigate http://localhost:8931/stocks/NVDA.html; template transform + real
      client module applied in-page with the route stubbed by the real payload
  - claim: >
      38 focused tests pass; the existing dossier guards still pass; static
      guards clean.
    command: >
      python3 -m pytest tests/test_dossier_quote_api.py
      tests/test_dossier_live_quote_surface.py
      tests/test_check_stock_dossier_integrity.py
      tests/test_company_intelligence_dossier_js.py -q
  - claim: >
      Template compiles and renders the exact markup the client binds to, with
      nb-px absent from the output — so what render.yml emits matches the
      contract.
    command: >
      python3 -c "from jinja2 import Environment, FileSystemLoader; ..." rendering
      templates/ticker.html.j2 with a minimal hero context
  - claim: >
      Deploy path: app/*.py is inside the macro-api restart regex
      (app/deploy/update.sh:1234); templates/ticker.html.j2 is in render.yml's
      scope whitelist (line 544 -> scope `macro`); /api/* is excluded from both
      the regwall and paywall matchers, so the route is public.
    command: >
      grep -n "app/.*\.py" app/deploy/update.sh; grep -n "ticker.html.j2"
      .github/workflows/render.yml; grep -n "not path /api" app/deploy/Caddyfile
unverified:
  - >
    The realtime verdict itself. The US regular session was closed throughout, so
    the `live` branch is proven by unit test, by mutation, and in a browser
    against a synthetic realtime payload — but never against a genuinely realtime
    production feed. This is the BUILT_NOT_PROVEN_NATURAL_TIME_GATE the
    commission anticipated.
  - >
    Whether production currently emits a `chg` that disagrees with
    (last-prevClose)/prevClose. The consistency guard added after review makes the
    mismatch unshippable either way, but the mismatch was never observed live.
unresolved:
  - >
    HUB_REALTIME_QUOTES is a shared entitlement switch, not the quote-freshness
    lever the commission took it for. Needs a Sol/Chairman ruling before it is
    set. Detail in the "Exact remaining gate" section below.
  - >
    templates/intelligence_hub.html.j2:400 carries the same class of decorative
    "Live" claim (driven by the build, not a quote). Different surface, outside
    the frozen P0 scope, deliberately not touched.
  - >
    site/stocks/*.html <meta name="description"> and og:description bake
    "Price: $209.66"; nothing repaints them, so a share card can contradict the
    page. Pre-existing, not introduced here, not in scope.
  - >
    ACCEPTED RESIDUAL — on a STALE-build page there is no quote stamp at all.
    templates/ticker.html.j2 puts `data-dq-stamp` only in the not-stale branch,
    while the price nodes are unconditional, so a stale build repaints to a
    current price under a header still reading "May be stale · <build date>".
    Deliberately NOT fixed: that chip is about the page DATA (stance,
    technicals) going old, which stays true even when the price is current, and
    overwriting it would hide a real warning. Adding a second chip is a UI
    change to a rare branch I could not visually verify. The ambiguity is mild
    and in the safe direction; a successor with a stale-build page in hand
    should show BOTH claims rather than letting one overwrite the other.
  - >
    ACCEPTED RESIDUAL — clock-skew asymmetry. `_freshness_of` rejects a stamp
    more than _LIVE_MAX_AGE_SECONDS in the FUTURE, so +119s reads `live` and
    +121s reads `stale` (which the client paints "Not updating") on an
    otherwise healthy feed. Both directions are untested. A tolerance band has
    to sit somewhere; this one errs toward refusing rather than claiming.
  - >
    ACCEPTED RESIDUAL — `_HUB_TIMEOUT_SECONDS` bounds each socket operation,
    not the whole read, so a peer trickling bytes could hold a worker thread
    (the route is a sync `def` on Starlette's thread pool). Mitigated by the
    loopback assertion and the redirect refusal — the only peer that can do
    this is our own hub on 127.0.0.1 — but an overall deadline would close it
    properly.
next_actions:
  - >
    Obtain the Sol/Chairman ruling on HUB_REALTIME_QUOTES, then flip it just
    before a US regular-session open where the realtime verdict is measurable.
  - >
    Re-verify the dossier during an open RTH to close the natural time gate.
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
