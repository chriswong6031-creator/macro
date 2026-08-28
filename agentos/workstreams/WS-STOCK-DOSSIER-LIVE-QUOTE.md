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
  publisher. Done when P0 is merged, rendered and verified live, and the one
  open entitlement ruling below is answered.
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
    status: in_progress
    pr: 6572
    next_action: >
      PR #6572 merged as 033f929087a03d2931d47e1f2ea0e4f39a9cf3bb, but P0 is not done.
      Obtain the required open-US-session production proof and settle the shared
      HUB_REALTIME_QUOTES entitlement ruling before marking this wave complete.
  - id: P1
    title: Not commissioned — Sol owns scoping; see DEC/handoff before starting
    status: todo
next_action: >
  Sol/Chairman ruling on HUB_REALTIME_QUOTES (see next_actions[0]) — it is a
  shared entitlement switch, not the quote-freshness lever the P0 commission
  took it for, so P0 deliberately left it unset. Then re-verify the dossier on a
  real open US session before closing P0; P1 remains uncommissioned.
next_actions:
  - >
    RULING NEEDED (Sol/Chairman): the P0 commission authorized setting
    HUB_REALTIME_QUOTES=1 on the Terminal env, believing it a quote-freshness
    lever. It is not — it is also read by terminal/app/api/intraday/route.ts and
    unlocks the Terminal's 1s/5s/15s/30s bar band, and hub/README.md states it is
    deliberately the single switch a PENDING anonymous-vs-sign-in ruling is meant
    to land on. It was therefore NOT set. Answer whether unlocking the seconds
    band is intended; if yes, flip it just before a US regular-session open,
    where the realtime verdict can actually be measured.
  - >
    Re-verify the dossier during an OPEN US regular session to obtain the
    realtime verdict P0 could not: the session was closed at build time, so the
    `live` branch is proven by construction and in-browser, but not yet observed
    against a genuinely realtime production feed.
do_not_redo:
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
