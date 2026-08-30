---
key: STOCK-DOSSIER-LIVE-QUOTE
title: Static stock dossiers show a current, honestly-labelled US quote
objective: >
  Every US dossier built from templates/ticker.html.j2 shows the same current
  regular-session quote plane as Terminal — price plus absolute/percent move
  repainted from the Terminal Quote Plane — and the page says "Live" ONLY when
  the quote itself proves measured current freshness. The nightly HTML remains
  an honest dated fallback, never a fake-live value. Market-data authority stays
  with the Terminal Quote Plane; this workstream never becomes a second
  publisher. P0/P0b implementation is complete at its bounded code/runtime
  scope; final CEO acceptance keeps user-visible proof and historical authority
  provenance as separate gates.
status: active
# The capability being consumed is the Terminal Quote Plane, and the standing
# law is that market-data authority stays there — this workstream is a Macro-side
# CONSUMER of that program, never a second publisher.
program: terminal-market-data
repos: [macro, terminal]
owner: unassigned
class: build
blast_radius: user_facing
ambiguity: specified
waves:
  - id: P0
    title: Bounded dossier quote projection + honest freshness stamp
    status: done
    pr: 6572
  - id: P0b
    title: Measured realtime enabled; rolled-anchor zero-move fixed
    status: done
    pr: 6617
  - id: P1
    title: Not commissioned — Sol owns scoping; see DEC/handoff before starting
    status: todo
next_action: >
  CEO-only closeout. Preserve the current runtime; do not toggle or restart the
  Terminal quote plane merely to repair historical records. Obtain one untouched
  user-visible dossier proof in an open RTH window and one untouched non-RTH
  proof when practical, so the real visibility/background-tab path and the
  rolled-anchor behavior are observed without a headless visibility override.
  Historical authority for the 2026-08-28 `HUB_REALTIME_QUOTES=1` mutation stays
  unresolved unless an independent post-DO-NOT-SET Chairman/Executive authority
  receipt is recovered; see
  DSC:STOCK-DOSSIER-REALTIME-AUTHORITY-PROVENANCE. The optional pre-market
  Terminal question remains a separate future commission.
next_actions:
  - >
    CEO acceptance proof only, no runtime mutation: on an untouched browser tab,
    verify the served dossier consumes the current Terminal quote plane and uses
    an honest freshness/session label during one open RTH window; separately
    observe one non-RTH window and verify the rolled-anchor repair does not
    regress the displayed move to +0.00% / $0.00. Record the real page state and
    current quote-plane evidence; do not force `document.hidden` or synthesize a
    market state.
  - >
    OPTIONAL, Terminal repo, needs its own commission: the dossier cannot show a
    realtime PRE-MARKET price. Polygon zeroes the whole `day` block before
    09:30 ET and hub/lib/snapshot.js parseSnapshot() returns null on
    `day.c <= 0`, so every US row is discarded pre-market even with the realtime
    leg on. The row still carries a usable print (measured 2026-08-28 11:43Z:
    lastTrade 24 s old, plus a 1-minute bar). `day` semantics are
    regular-session on purpose, so this is a deliberate design question, not a
    bug to patch in passing.
resolved_actions:
  - >
    EFFECT RESOLVED / AUTHORITY PROVENANCE UNRESOLVED — On 2026-08-28
    `HUB_REALTIME_QUOTES=1` was set in `/opt/terminal/.env` (backup
    `.env.bak-20260828-dossier-live`) and quote-hub was restarted. Production
    evidence later proved the realtime snapshot leg and measured freshness path
    worked. The technical correction behind the earlier deferral is also real:
    quote-hub.service receives `/opt/terminal/.env`, while the separate Terminal
    process does not receive that value through the same systemd EnvironmentFile,
    so this runtime flag did not by itself enable the Terminal seconds-band UI.
    HOWEVER the historical modifying authority is not independently proven by
    the current estate. The original P0 carrier explicitly said DO NOT SET the
    flag and moved realtime/access policy to a separate future operation. The
    later handoff quotes an operator directive but cites no independently
    recoverable authority receipt. Preserve the successful effect without
    retroactively calling it P0-authorized; see
    DSC:STOCK-DOSSIER-REALTIME-AUTHORITY-PROVENANCE.
  - >
    RESOLVED 2026-08-28 — the realtime verdict P0 could not obtain was observed
    in production 46 s after the opening bell: hub verdict
    {tier:"realtime", floorLagMs:153.77}, route freshness "live" / session
    "regular", and the served page repainted 227.98→226.82 with the move, the
    sign, both language strings and the green pulse moving together. This proves
    runtime/data-path behavior; the browser capture still used a visibility
    override, so untouched final user-visible acceptance remains the next action
    above.
do_not_redo:
  - >
    Do NOT use successful runtime behavior, the merged #6619 records PR, or the
    2026-08-28 operator handoff's quoted directive as a substitute for an
    independently recoverable authority receipt. Effect truth and authority
    provenance are different facts. See
    DSC:STOCK-DOSSIER-REALTIME-AUTHORITY-PROVENANCE. Do not roll back the runtime
    solely to make the historical record cleaner; rollback is another modifying
    operation and requires current authority/current Terminal evidence.
  - >
    Do NOT read the Quote Hub contract out of the charting-app checkout on the
    fleet host. It sat on claude/terminal-audit-fixes-20260713 and does not
    contain the code production runs (no snapshot leg, no HUB_REALTIME_QUOTES,
    US rows stamped polygon-delayed rather than polygon-snapshot). Probe the
    running service. See DSC:QUOTE-HUB-CHG-IS-PERCENT-AND-TS-IS-A-PRINT-CLOCK.
  - >
    Do NOT re-add the dossier hero/sticky price to the shared .nb-px selector.
    live.js owns that selector and resolves its snapshot RELATIVE, which from
    /stocks/ is /stocks/live/quotes.json — a path that does not exist. Two owners
    on one node is a race decided by fetch order.
danger_areas:
  - >
    The percent cross-check in `_public_projection` compares upstream's `chg`
    against the percent implied by last/prevClose and, on disagreement, derives
    both from the price pair. It CANNOT notice that its two inputs are the SAME
    number. Outside RTH upstream's anchor rolls forward until prevClose == last,
    so that rule measured the close against itself and published
    `+$0.00 · +0.00%` on every US dossier (measured 2026-08-28 11:43Z; fixed in
    #6617 via prevSessionChg). Any future consistency rule here needs an
    explicit degenerate-case check.
  - >
    Enabling HUB_REALTIME_QUOTES appears to do nothing until 09:30 ET: /health
    shows realtime true, ttlMs 8000, cache filling, errors 0, while
    verdict.tier stays "unknown" and rows keep DELAYED_15M. That is the design
    (see next_actions[1]), not a broken flag — do not go looking for a fault.
  - >
    `regularSession` is the STATE of the regular session ("rth" while open,
    "closed" after the bell), NOT the session a print came from. Reading it the
    second way and refusing non-"rth" rows 503'd every US dossier overnight
    (shipped in #6572, fixed in #6592). The closed row still carries the correct
    settled close, which is exactly what an overnight dossier must show.
  - >
    Test fixtures here are live captures. The original was taken during RTH, so
    every test agreed the market was open and nothing exercised the closed
    state — which is what the page is in for most of the day. Any new fixture
    must be paired with one from the opposite session state.
  - >
    `chg` from the hub is a PERCENT, not the dollar move, and `ts` is the
    vendor's print clock that stops advancing after the close. Both mis-readings
    render a plausible number and raise nothing.
  - >
    Any staleness bound here must stay session-aware. A flat bound marks a
    correct settled after-hours close "stale" minutes after the bell and reverts
    the page to its baked value — which is the original defect returning.
  - >
    engine/live_quotes.py, templates/live.js and site/live.js belong to PR #6390.
    P0 deliberately did not touch them.
owns_paths:
  - app/dossier_quote.py
  - site/assets/js/dossier-live-quote.js
  - templates/ticker.html.j2
---

P0 fixed a user-facing truth defect, not a lag: `/stocks/NVDA.html` served a
baked $209.66 with a static `-$3.39 · -1.59%` under a pulsing green "Live" chip,
while the measured regular-session close was $227.98 (+8.74%). The baked figure
was the row's own `prevClose`, so the page showed the previous close and the
previous day's move — an inverted sign — and called it live. The chip was keyed
off the build's `stale` flag: a claim about the render presented as a claim about
the market.

The governing law the successor must preserve: `freshness` describes the FEED,
`session` describes the MARKET, and "Live" requires both. Every uncertainty
resolves downward, and an upstream fault is a 503 rather than a 200 carrying a
plausible price.
