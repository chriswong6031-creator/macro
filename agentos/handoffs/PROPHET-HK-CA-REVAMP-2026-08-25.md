---
workstream: WS:PROPHET-HK-CA-REVAMP
session: fable/stock-v36-rollout-reconciliation-20260825
model: fable
ended_because: blocked
prs: [6398]
mission: >
  Resume the Stock Dashboard V3.6 presentation lane: recover the real V3.6
  design authority, settle the Canada V3.6.1 production-acceptance gate as far
  as lawfully possible, prepare (not execute) the gated HK V3.6 follower, and
  deliver the cross-market convergence packet Sol needs before any US
  presentation architecture is frozen.
state_before: >
  Canada V3.6 merged (#6315) + V3.6.1 hierarchy correction merged (#6327),
  classified BUILT_NOT_PROVEN by the 2026-08-23 Sol handoff with two proof
  legs owed (release identity; entitled browser matrix). HK V3.6 gated on
  Canada production acceptance. No V3.6 masterplan located; no collision
  ledger; no Canada→HK disposition table; no US/V4/Cell-H reconciliation.
changed:
  - path: research/STOCK_DASHBOARD_V36_CANADA_ACCEPTANCE_2026-08-25.md
    what: >
      Canada V3.6.1 acceptance record: leg 1 (release identity) PROVEN with
      VPS receipts; leg 2 (entitled browser matrix) BLOCKED on operator-side
      entitled session; access-boundary facts; anonymous fallback
      observations; the exact owed matrix.
  - path: research/STOCK_DASHBOARD_V36_CROSS_MARKET_CONVERGENCE_PACKET_2026-08-25.md
    what: >
      The Sol convergence packet: recovered V3.6 design authority (PR bodies
      ARE the masterplan; Canada→HK recorded, HK→US NOT recorded), shipped
      grammar, market deltas, Canada→HK capability disposition table
      (pre-build), US 50-capability overlay with rulings, V4 plane
      boundaries, Cell H disposition (off-main provenance flagged), one
      recommended US architecture with freeze gates and a kill list.
verified:
  - claim: Production serves a main descendant containing both Canada V3.6 merges.
    command: >
      ssh (deploy key) root@146.190.142.17 'cd /opt/macro && git rev-parse
      HEAD && curl -s http://127.0.0.1:8000/api/health'; local
      git merge-base --is-ancestor for b14f1f4186a8 and 5a8f6a5aa98b.
    result: >
      /opt/macro HEAD = ce4a33aeeed7 = origin/main at probe time; api/health
      checkout matches; both merges are ancestors. Served bytes chain
      canada_stocks.html → dashboard-icons.js?v=d72d8b14 →
      canada-stock-v36.js?v=20260823 with the V3.6.1 Prophet-first order.
  - claim: The anonymous production journey degrades exactly as designed.
    command: >
      In-app browser on https://mastermind-x.com/canada_stocks.html; DOM
      probes for v36 markers, pvcards, overflow; console read; in-page fetch
      of the gated asset.
    result: >
      canada-stock-v36.js returns 401 anonymously (reviewed boundary
      intact); composer does not engage; legacy page fully functional
      (10 pvcards, populated lanes, no overflow, no duplicate board).
      Anonymous console shows the expected 401 + MIME-refusal noise
      (nonblocking observation recorded).
  - claim: No open PR collides with the V3.6/HK/Canada presentation surfaces.
    command: >
      gh pr list --state open --limit 60 + gh search prs for
      canada-stock-v36.js / hk.html.j2 / dashboard-icons.js / stocktable.js;
      git log --since=2026-08-20 over the shared presentation surfaces.
    result: Zero open PRs touch any of them; only #6315/#6327 touched V3.6 files.
unverified:
  - claim: The entitled Canada V3.6.1 browser journey is correct end to end.
    what_would_verify: >
      The signed-in matrix in the acceptance record (dark/light · EN/ZH ·
      desktop/390px · hierarchy · Top Picks/All Candidates · Grid/Table ·
      leadership filter/modal · live quotes · dual clocks · StockTable
      controls · Terminal routing · single board · clean console · no
      overflow) run in a real entitled session — Claude-in-Chrome with the
      operator's session, or the operator by hand.
unresolved:
  - "Canada stays BUILT_NOT_PROVEN: leg 2 needs an entitled session an autonomous agent cannot lawfully create (credential entry prohibited; Claude-in-Chrome disconnected all session; no reviewed non-credential probe path exists, correctly)."
  - "HK V3.6 remains lawfully unreleased until Canada leg 2 passes; the build is fully prepared (disposition table + build-shape ruling in the convergence packet §4)."
  - "HK→US rollout sequence is NOT durably recorded anywhere; only Canada→HK is law. Sol must ratify or decouple (packet §8.2)."
  - "Cell H experience research is off-main (sol/prophet-flagship-fanout-hardening-20260822 only); merge/ratify before any US freeze cites it (packet §8.5)."
  - "The 08-23 handoff's 'regional experience architecture was frozen' claim has no DEC record; the missing durable records are listed in packet §8.3."
next_actions:
  - "Operator: provide an entitled session (connect Claude-in-Chrome, or run the matrix by hand per research/STOCK_DASHBOARD_V36_CANADA_ACCEPTANCE_2026-08-25.md) — this is the single lever unblocking the lane."
  - "On leg-2 PASS: promote Canada to PROVEN_LIVE in a dated receipt, then release the HK V3.6 presentation coding wave executing packet §4 (new hk-stock-v36.js; RETAIN rows binding; no writes to hk_standouts.json/build_hk_library.py; keep ZH tape swap; no fabricated LIVE chip)."
  - "On leg-2 FAIL: repair Canada only, re-prove, do not start HK."
  - "Sol: adjudicate packet §8 (sequence ratification, Cell H provenance, US hierarchy doctrine, US freeze gates). Do not commission any US implementation before the §7 gates."
do_not_redo:
  - "Do not re-run the Phase A archaeology: the V3.6 masterplan does not exist as a document; PR #6315/#6327 bodies + the 08-23 handoff are the complete design authority (searched: macro research/, agentos/, mockups/, verify_shots/, Mastermind tracked tree, both SOL operation IDs — zero hits)."
  - "Do not make canada-stock-v36.js (or a future hk-stock-v36.js) anonymously public to simplify probing; the 401-anonymous boundary is reviewed design."
  - "Do not port Canada's Western-tape-under-ZH pin to HK; the site-wide ZH swap is HK-native truth."
  - "Do not give HK a client-clock LIVE chip; HK has no live quote plane today."
  - "Do not apply the V3.6 client-composer pattern to the US page; US tiering is server-split+hydration and four named collisions exist (packet §5)."
danger_areas:
  - "The intelligence lane owns scripts/build_hk_library.py and hk_standouts.json (HK Brain consumes the latter — publishing to it is an authority transition). The HK V3.6 wave edits neither."
  - "scripts/build_canada.py is dual-role (intelligence-owned, also renders the page); the HK analogue build_hk.py is NOT intelligence-owned — keep it that way."
  - "The V3.6 composer's DOM selectors are Canada-specific (#standouts .cards); HK's grid scaffolding differs — an HK follower adapts selectors, never templates."
  - "US anonymous shell bakes preview_rows=3 per population; any first-N concentration rule is unfillable there — use the Featured cohort."
---

# Return point

Canada V3.6.1: leg 1 (release identity) is PROVEN with receipts; leg 2
(entitled browser matrix) is the single remaining gate and needs an
operator-side entitled session. HK V3.6 is fully prepared and lawfully
unreleased. The cross-market convergence packet for Sol is
`research/STOCK_DASHBOARD_V36_CROSS_MARKET_CONVERGENCE_PACKET_2026-08-25.md`;
its §8 lists every decision that needs Sol/Chairman. No intelligence,
ranking, lifecycle, availability, entitlement, or quote semantics were touched
by this session.
