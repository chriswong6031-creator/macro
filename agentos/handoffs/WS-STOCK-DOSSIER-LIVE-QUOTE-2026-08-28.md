---
workstream: "WS:STOCK-DOSSIER-LIVE-QUOTE"
session: "claude/dossier-quote-session-move (worktree stock-dossier-live-quote-dae491)"
model: opus
ended_because: complete
mission: >
  Operator directive 2026-08-28: "Need to fix the delayed thing, so that its
  live. you are authorized to conduct any changes needed." Make the dossier
  quote report measured-realtime rather than delayed, and prove it on the served
  page during an open US regular session.
state_before: >
  P0 shipped an honest freshness plane but the feed behind it was 15-minute
  delayed, so /api/dossier-quote/{ticker} could only ever answer freshness
  "delayed" — the page never said "Live" because it was never entitled to.
  Separately, and undiscovered until this session probed production, every US
  dossier was serving `change_abs 0.0, change_pct 0.0` outside RTH.
changed:
  - path: "/opt/terminal/.env (VPS runtime, no PR)"
    what: >
      Appended HUB_REALTIME_QUOTES=1 and restarted quote-hub. Backup at
      /opt/terminal/.env.bak-20260828-dossier-live. This enables the REST
      snapshot leg's 8s poll and last-trade parse. It does NOT label anything:
      hub/lib/snapshot.js verdict() measures the print-age floor against the
      wall clock and store.js stamps basis from THAT, so on a delayed plan the
      floor would measure ~15 min and rows would keep DELAYED_15M. The flag
      therefore cannot manufacture a false "Live" — which is what made flipping
      it safe. HUB_POLYGON_CLUSTER deliberately left at `delayed`; the snapshot
      leg is REST, so no second WebSocket owner is created.
  - path: app/dossier_quote.py
    what: >
      PR 6617. Prefer `prevSessionChg` when upstream publishes it, and
      reconstruct the anchor as price / (1 + pct/100). Outside RTH upstream
      advances its anchor to the last settled close, so prevClose == last and
      the derived move is exactly zero; upstream deletes prevSessionChg the
      moment today's session is in hand, which makes its presence the signal.
      Guarded by `ratio > 0` ALONE — at exactly -100% the ratio is 0 and the
      division raises, below it the anchor is not a price. A second guard on the
      quotient was written, then removed: unreachable behind the first, so no
      mutation could prove it was still there.
  - path: tests/test_dossier_quote_api.py
    what: >
      PR 6617. Adds HUB_NVDA_PREMARKET, a verbatim capture at 11:43Z in the
      session state opposite the existing RTH fixture, plus 4 tests and one
      8-way parametrize.
verified:
  - claim: >
      ENTITLEMENT, established BEFORE changing anything: the production key is
      already receiving real-time prints. Last-trade age across 8 liquid names
      floored at 24.1 s (TSLA 24.3, NVDA 24.1, AAPL 24.3, QQQ 46.5, AMZN 64.9,
      MSFT 86.4, SPY 139.5, AMD 188.2). A 15-minute-delayed plan cannot produce
      a 24-second-old print for ANY symbol, which is exactly why the hub
      measures the floor rather than one ticker.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'set -a; .
      /opt/terminal/.env; set +a; curl -s
      "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?tickers=NVDA,AAPL,MSFT,TSLA,AMD,SPY,QQQ,AMZN&apiKey=$POLYGON_API_KEY"'
      then python3 comparing lastTrade.t (nanoseconds) to time.time()
  - claim: >
      Realtime leg enabled and healthy after restart: snapshotFeed.realtime
      true, ttlMs 60000 -> 8000, errors 0.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'curl -s
      http://127.0.0.1:3100/health'
  - claim: >
      At 13:30:46Z, 46 s after the opening bell, the hub graded ITSELF realtime:
      verdict {tier: "realtime", floorLagMs: 153.77} — a 153-millisecond
      print-age floor. Pre-market the same probe read tier "unknown" with
      floorLagMs null, which is the documented day.c == 0 behaviour.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'curl -s
      http://127.0.0.1:3100/health' via an armed 240 s Monitor across the open
  - claim: >
      Route answers live during the regular session: {"freshness":"live",
      "session":"regular","price":226.6599,"change_pct":-0.579,
      "regular_session_date":"2026-08-28"}. Also reachable from the page's own
      origin, so routing and CORS are not in the way.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'curl -s
      http://127.0.0.1:8000/api/dossier-quote/NVDA' and, in-page,
      fetch('/api/dossier-quote/NVDA')
  - claim: >
      Served page repaint, every element moving together from ONE quote:
      price (hero AND sticky) 227.98 -> 226.82; move +$18.32/+8.74% ->
      -$1.16/-0.51%; stamp data-dq-state baked -> live; stamp text "As of
      2026-08-28/截至" -> "Live/实时" (both language strings set); move class
      px-chg pos -> px-chg neg; pip animation none -> v6lp; pip colour grey ->
      rgb(61,165,100). See `unverified` for the visibility caveat on this
      capture.
    command: >
      mcp__Claude_Browser__javascript_tool on
      https://mastermind-x.com/stocks/NVDA.html, reading [data-dq-sym],
      [data-dq-abs], [data-dq-pct], [data-dq-stamp], [data-dq-chg] and
      getComputedStyle(.live-dot) before and after
  - claim: "Both dossier suites green: 68 passed (50 in the API suite, 18 in the surface suite)."
    command: "python3 -m pytest tests/test_dossier_quote_api.py tests/test_dossier_live_quote_surface.py -q"
  - claim: >
      Test discrimination proven, not assumed: 7 independent mutations of the
      fix, applied against the COMMITTED baseline, each turn the suite RED —
      drop the reconstruction (3 failed), divide -> multiply (3), magnitude of
      the move (1), ratio > 0 -> ratio != 0 (2), guard removed (3), sign flip
      (3), read `chg` instead of `prevSessionChg` (3).
    command: >
      python3 patch app/dossier_quote.py; python3 -m pytest
      tests/test_dossier_quote_api.py -q; git checkout -- app/dossier_quote.py
      (per mutation, looped)
  - claim: >
      PR 6617 CI concluded 35 pass, 3 skipping, 1 fail. The single fail is
      ci-authority/codex/merge-queue-pilot, and its own output summary reads
      allowed:true, reason:"ordinary_change", context_active:false,
      context_reason:"inactive_base_context" — non-binding, and
      authority_hit_count 0 for the 2 changed files.
    command: >
      gh pr checks 6617 --json name,bucket and gh api
      repos/mastermindx-market-intelligence/macro/check-runs/98841664138 --jq
      '.output.summary'
  - claim: >
      Merged 98be5f10 at 15:38:52Z and DEPLOYED: prevSessionChg present in the
      VPS copy of the module, macro-api restarted 15:39:15Z (23 s after merge),
      route returns HTTP 200. An immediately-following probe returned empty —
      that was curl racing the uvicorn boot, not a fault; the re-probe was 200.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17 'grep -q
      prevSessionChg /opt/macro/app/dossier_quote.py; systemctl is-active
      macro-api; curl -s -w "\nHTTP=%{http_code}\n"
      http://127.0.0.1:8000/api/dossier-quote/NVDA'
unverified:
  - >
    The browser capture is NOT untouched. The headless preview pane hard-reports
    every tab as document.hidden, so the client's (correct) background-tab
    stand-down never lifts and the page sits on baked values indefinitely. No
    Chrome was connected to use instead. document.hidden / visibilityState were
    overridden and visibilitychange dispatched: the script, endpoint, live data
    and DOM mutation are all real, only the visibility signal was supplied. A
    human glance at the page during market hours closes this gap in seconds.
  - >
    The rolled-anchor fix is merged and deployed but has NOT been observed
    firing in production, because prevSessionChg is absent during RTH and the
    fix is inert then. First real exercise is the next post-close or pre-open
    window; expected is the last settled close with the previous session's move
    beside it rather than +$0.00 and +0.00%.
unresolved:
  - >
    The dossier cannot show a realtime PRE-MARKET price. Terminal-repo question,
    needs its own commission — see next_actions.
next_actions:
  - >
    OPTIONAL, Terminal repo, own commission: Polygon zeroes the whole `day`
    block before 09:30 ET and hub/lib/snapshot.js parseSnapshot() returns null
    on `day.c <= 0`, so every US row is discarded pre-market even with the
    realtime leg enabled. The row still carries a usable print (measured
    2026-08-28 11:43Z: lastTrade 24 s old, plus a 1-minute bar at 227.02).
    `day` semantics are regular-session on purpose, so this is a design question
    and not a bug to patch in passing.
  - >
    Confirm the rolled-anchor fix in the next non-RTH window (see unverified).
do_not_redo:
  - >
    Do NOT treat HUB_REALTIME_QUOTES as a shared entitlement switch on grep
    evidence. Terminal code DOES read it (page.tsx secondBarsEnabled,
    api/intraday/route.ts) and this workstream deferred it for a day on that
    basis. That was wrong: quote-hub.service carries
    EnvironmentFile=/opt/terminal/.env, terminal.service carries NO
    EnvironmentFile at all, and Next.js loads env from its own project root one
    directory below. Grep says who READS a name; only `systemctl cat` says who
    RECEIVES the value.
  - >
    Do NOT hunt for a fault when the flag appears inert. /health showing
    realtime true, ttlMs 8000, cache filling, errors 0, while verdict.tier stays
    "unknown" and rows keep DELAYED_15M, is the documented pre-market behaviour.
    It clears itself at the bell.
  - >
    Do NOT add a second guard on the reconstructed anchor. It is unreachable
    behind `ratio > 0`, so no mutation can prove it is present, and an assertion
    nothing can falsify is decoration rather than safety.
danger_areas:
  - >
    The percent cross-check in _public_projection compares upstream's `chg`
    against the percent implied by last/prevClose and, on disagreement, derives
    both from the price pair. It CANNOT notice that its two inputs are the same
    number — which is exactly how it published +$0.00 and +0.00% on every US
    dossier. Any future consistency rule here needs an explicit degenerate-case
    check.
  - >
    Fixtures here are live captures and each freezes ONE market state.
    HUB_NVDA_DELAYED is RTH, HUB_NVDA_PREMARKET is pre-open. Any new fixture
    must be paired with one from the opposite state — the 2026-08-27 503 shipped
    precisely because every fixture agreed the market was open.
  - >
    A mutation harness that reverts with `git checkout -- <file>` will silently
    revert your own UNCOMMITTED edit and then test the old code, reporting
    survivors that are really just the previous implementation. Commit first,
    and assert the mutation target string was actually found.
  - >
    A CI watcher gating on `npack >= 12` never fires on a PR whose packs have
    not registered yet, and `pending == 0` alone exits BEFORE the fan-out
    appears. Both failure modes hit this session. Require pending == 0 to hold
    across two passes about 180 s apart.
---

# Summary

Two things shipped: the quote plane became genuinely realtime (a runtime change,
no PR), and a zero-move defect introduced by P0 was found and fixed (PR 6617,
merged 98be5f10).

The load-bearing design property, worth preserving: **the hub grades itself.**
`HUB_REALTIME_QUOTES` only enables the leg. The "Live" label comes from
`verdict()` measuring print age against the wall clock, so a wrong entitlement
produces "Delayed", never a false "Live". That is why this flag could be flipped
on measured evidence rather than waiting on a ruling.

The zero-move bug is the more instructive one. P0's percent cross-check exists to
stop a dollar move from one session appearing beside a percent from another. It
works by preferring the internally consistent pair. Outside RTH the anchor rolls
forward until `prevClose == last`, and measuring a close against itself is
perfectly consistent — so the guard discarded upstream's correct +8.74% in
favour of a self-derived 0.00%. A consistency check cannot see that its two
inputs are one input.
