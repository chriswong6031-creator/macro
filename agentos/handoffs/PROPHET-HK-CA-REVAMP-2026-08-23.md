---
workstream: WS:PROPHET-HK-CA-REVAMP
session: sol/stock-v36-canada-closeout-20260823
model: sol
ended_because: blocked
prs: [6315]
mission: >
  Record the Chairman-approved Canada Stock Dashboard V3.6 presentation pilot after
  merge, preserve its no-rebuild/authority boundaries, and prevent the next regional
  presentation wave from treating merge/render success as production acceptance.
state_before: >
  The regional stock-dashboard experience architecture was frozen, Canada was selected
  as the first presentation-only pilot, and PR #6315 had reached a mergeable exact head
  after adversarial source/data-shape review. Production acceptance still required the
  private runtime identity probes and a signed-in browser matrix.
changed:
  - path: site/canada-stock-v36.js
    what: >
      PR #6315 added the Canada-only progressive V3.6 composer. It re-composes the
      existing Prophet cards and StockTable, uses canonical Canada board order for the
      first five Top Picks, uses the published basket membership plus sector-pulse rank
      and recommendation artifacts for leadership, applies SF/system UI ticker type,
      preserves Canada green-up/red-down tape convention, and leaves the legacy board
      visible if required inputs fail.
  - path: templates/dashboard-icons.js
    what: >
      PR #6315 added the strict canada_stocks.html-only loader for the V3.6 composer;
      no other page loads the new bundle.
  - path: site/dashboard-icons.js
    what: >
      PR #6315 shipped the production-tree twin of the same strict loader. A later
      post-merge render-sync re-stamped canada_stocks.html to the new shared-asset hash.
  - path: agentos/handoffs/PROPHET-HK-CA-REVAMP-2026-08-23.md
    what: >
      Records immutable merge/render receipts, the remaining production-proof gate,
      presentation no-rebuild boundaries, and the exact continuation condition.
verified:
  - claim: PR #6315 merged from the reviewed exact head after hosted CI and fences passed.
    command: >
      Read GitHub PR #6315, exact head 8f04e0def3c8b2d1329915aed4c9c5bd372b9c5e,
      its commit workflow runs, and the squash merge result.
    result: >
      Hosted ci run 12933 and fences run 12990 both concluded success on the exact
      reviewed head. GitHub squash-merged #6315 as
      b14f1f4186a84e8dead509692934aed38c0dab0e.
  - claim: The Canada merge remains in current main after later automated descendants.
    command: >
      Compare b14f1f4186a84e8dead509692934aed38c0dab0e to current-main pin
      0e38c48b38e7b2a10c55e3218f691bd83d8f4f65 with GitHub compare_commits.
    result: >
      Status ahead, behind_by=0, with b14f1f4 as merge base; current main is a direct
      descendant of the Canada merge.
  - claim: The real post-merge rendered Canada page references the new shared loader asset.
    command: >
      Read site/canada_stocks.html and site/dashboard-icons.js at
      0e38c48b38e7b2a10c55e3218f691bd83d8f4f65.
    result: >
      Rendered Canada HTML loads dashboard-icons.js?v=d72d8b14, and that current
      site/dashboard-icons.js contains the strict Canada-only loader for
      canada-stock-v36.js?v=20260823.
  - claim: The V3.6 presentation does not become a new Prophet or market-authority owner.
    command: >
      Read site/canada-stock-v36.js at merge SHA
      b14f1f4186a84e8dead509692934aed38c0dab0e and the PR #6315 changed-file set.
    result: >
      The diff is limited to the V3 composer plus loader twins. The composer explicitly
      owns no rank, signal, quote, lifecycle, entitlement, or persistence semantics;
      it consumes existing Canada artifacts and moves existing pvcard/StockTable DOM.
unverified:
  - claim: The production VPS is currently serving a main descendant that contains the Canada V3.6 merge.
    what_would_verify: >
      Authenticated/on-host runtime collection proving /opt/macro HEAD and local
      /api/health.commit are b14f1f4 or a descendant containing it, using the canonical
      config/production_topology.yml release probes.
  - claim: The signed-in Canada V3.6 browser journey is correct end to end.
    what_would_verify: >
      Open real production canada_stocks.html in an entitled session and verify no
      duplicate legacy board; dark/light; EN/ZH; desktop/390px; non-empty Themes and
      Sectors; real row filtering; Top Picks/All Candidates; existing table filters;
      live quote/change patching; and the existing Terminal stock bridge.
unresolved:
  - "Canada remains BUILT_NOT_PROVEN until the private runtime identity and signed-in browser matrix are observed."
  - "The HK V3.6 presentation implementation must not start from Canada merge/render evidence alone; Canada production acceptance is the pilot gate."
  - "The workstream's separate hk-intel/ca-intel/ca-pit Prophet-intelligence waves retain their own commissioning authority and are not completed or blocked by this presentation handoff."
next_actions:
  - "Run the canonical authenticated production release probe for Macro and prove the deployed commit contains b14f1f4186a84e8dead509692934aed38c0dab0e."
  - "Run the signed-in Canada V3.6 browser matrix across dark/light, EN/ZH, desktop and 390px, including leadership filtering, Top Picks/All Candidates, table/live updates and Terminal routing."
  - "If and only if both production legs pass, promote Canada V3.6 from BUILT_NOT_PROVEN to PROVEN_LIVE in a dated durable receipt and release the HK V3.6 presentation coding wave."
  - "Do not conflate that HK presentation release gate with the workstream's separately commissioned hk-intel intelligence wave."
do_not_redo:
  - "Do not create another stock-card family; V3.6 reuses the existing Prophet pvcard family."
  - "Do not create a cross-market ranker, universal lifecycle, quote plane, entitlement plane, or stock truth store for the regional redesign."
  - "Do not derive Top Picks from a new browser score; Canada Top Picks are the first five rows of the canonical existing board order."
  - "Do not infer theme membership or theme ranking in the browser; use published basket membership and sector-pulse rank/recommendation state."
  - "Do not make canada-stock-v36.js anonymously public merely to simplify a production probe; preserve the reviewed static-asset access boundary."
  - "Do not add a bespoke CI workflow or unwired pytest suite for this presentation slice; the initial unowned-suite attempt was removed after contract-delta correctly rejected it."
  - "Do not call Canada PROVEN_LIVE from merge, green CI, post-merge render, or the three-minute deployment contract."
danger_areas:
  - "Selection is not action or authority: a Top Pick/Featured visual treatment must stay neutral and must not imply official-pick authority."
  - "The Canada basket artifact uses member symbol identity while other producers may use ticker; silently assuming one key can empty leadership filters."
  - "Legacy show-more visibility state can survive DOM moves; the composer explicitly clears it so All Candidates is complete."
  - "Registered static assets are default-deny outside the reviewed public allowlist; unauthenticated external fetch failure is not proof of failed deployment."
  - "A private runtime probe proves origin release identity, not signed-in browser composition; both proof legs are required."
---

# Return point

Canada Stock Dashboard V3.6 is merged and survives the real post-merge render path, but
its acceptance state is deliberately **BUILT_NOT_PROVEN**. The immutable implementation
receipt is PR #6315 / `b14f1f4186a84e8dead509692934aed38c0dab0e`; the post-merge rendered
Canada page on main references the newly stamped shared loader. The only remaining pilot
gate is production observation: canonical private release identity plus the entitled
browser journey. Preserve the existing Prophet intelligence wave graph; this handoff
records a presentation rollout and grants no new signal/ranking/promotion authority.
