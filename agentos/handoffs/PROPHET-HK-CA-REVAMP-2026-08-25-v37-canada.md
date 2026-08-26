---
workstream: WS:PROPHET-HK-CA-REVAMP
session: worktree-stock-dashboard-v3-6-rollout-d6f401 (Fable COO, V3.7 continuation)
model: fable
ended_because: complete
prs: [6416, 6425, 6409, 6410]
decisions:
  - DEC:V37-SUPERSEDES-V36-ACCEPTANCE
mission: >
  Execute the Sol V3.7 functional-completeness supersession on the existing
  Canada→HK regional rollout carrier: bootstrap the pinned Skillpack,
  reconcile the carrier, implement Canada V3.7 (Evidence & Record restore,
  owner-native lane vocabulary, group-action Expand Leadership, Sol-gate
  population law), adversarially review, merge, deploy, and prove on
  production; release the HK V3.7 follower wave.
state_before: >
  Canada V3.6.1 was PROVEN_LIVE (2026-08-25, historical) with #6409 loader
  retry and #6410 receipt still armed; an HK V3.6 builder had been stopped by
  the operator before pushing anything; Sol's continuation superseded V3.6
  acceptance with V3.7 functional completeness (artifacts not durable in
  either repo — handoff text + three Sol packets are authority); the fleet
  was intermittently red on ci-pack-9 from a malformed Defense handoff
  committed directly to main.
changed:
  - path: site/canada-stock-v36.js
    what: >
      V3.7 composer (PR #6416, merged 41efeba82b01): V3.7 constitution stamp;
      owner-native Act-Now lane vocabulary (verbatim EN+ZH from
      canada.html.j2:854-996); Evidence & Record panel that MOVES the .trk
      chip/dialog + Methodology link; group-action band in the Expand modal
      partitioned 1:1 by harvested lane on the existing delegation;
      leadership activation preserves population mode with an explicit
      bilingual zero-state + deliberate View All Candidates control.
  - path: tests/test_canada_v36_composer.py
    what: >
      Hardened discriminating pins — selector↔label lane binding, literal
      appendChild(trk) + exact id="ca-v36-evidence" + evidenceSectionHtml
      call-site count, live data-ca-modal-kind interpolation shape in both
      row builders, no-new-fetch invariant, activate()-never-switches pin;
      absorbed main's #6409 loader-retry pins via update-branch.
  - path: research/STOCK_DASHBOARD_V37_CANADA_ACCEPTANCE_2026-08-25.md
    what: Canada V3.7 PROVEN_LIVE acceptance record with the full production matrix and the Sol addendum-§16 ten-answer interrogation.
  - path: research/SOL_CANADA_V37_ADVERSARIAL_REVIEW_GATE.md
    what: Sol read-only review law, committed verbatim (delivered 2026-08-25 via operator; previously only in ~/Downloads).
  - path: research/SOL_V37_REFERENCE_ARTIFACT_PRODUCTION_ADDENDUM.md
    what: Sol read-only review law, committed verbatim (mockup owns composition only; producers own facts).
  - path: research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md
    what: Sol read-only HK follower architecture freeze, committed verbatim (HK gated on Canada V3.7 PROVEN_LIVE — now released).
  - path: agentos/decisions/DEC-V37-SUPERSEDES-V36-ACCEPTANCE.md
    what: The supersession ruling (acceptance target only; V3.6 regional rulings preserved).
verified:
  - claim: Canada V3.7 merged as the exact reviewed content
    command: git diff ba0f9fb3de1a 38c804cd19cc -- site/canada-stock-v36.js tests/test_canada_v36_composer.py
    result: composer byte-identical; test delta = main's own #6409 pins only; squash merge 41efeba82b0193dd9090c600567e0b551ad8dd98, ci.yml run 32911400774 SUCCESS
  - claim: Production serves the V3.7 composer
    command: ssh root@146.190.142.17 'cd /opt/macro && git log -1 --format=%H && grep -c "SOL-STOCK-DASH-V37\|ca-v36-evidence\|Buy Now\|ca-v36-empty-switch" site/canada-stock-v36.js'
    result: HEAD 9cebc0fff5af (merge descendant), all V3.7 markers present (9 matches)
  - claim: Entitled delivery cannot strand warm caches (review MAJOR-1)
    command: "in-page entitled fetch('/canada-stock-v36.js?v=20260823') — status + cache-control + body markers"
    result: 200, "private, no-store", V3.7 markers in body
  - claim: Sol-gate population law works end-to-end on production
    command: "entitled browser probe: activate theme ca_rails_ind while Top Picks active; then click .ca-v36-empty-switch"
    result: population stayed top, zero state 'No Top Picks in this group.该组别中暂无首选。' + View All Candidates; deliberate click switched to All showing exactly WSP.TO
  - claim: Evidence & Record is the real history owner, not a placeholder
    command: "entitled browser probe: click #trd-btn; fetch factordata/ca_track_ledger.json"
    result: dialog opens with real ledger rows (LNR.TO/LUN.TO/SAP.TO, accruing); ledger 200 private,no-store; Methodology → measurement.html live
  - claim: Full production matrix passing
    command: "entitled Claude-in-Chrome session probes + screenshots (dark/light, EN/ZH, XOR, workbench search/sort, console, overflow) — tabled in research/STOCK_DASHBOARD_V37_CANADA_ACCEPTANCE_2026-08-25.md"
    result: all cells PASS; zero console errors; zero overflow
unverified:
  - claim: Exact-390px production pixel pass
    what_would_verify: any human view or resizable window at 390px on production (bytes + local real-browser 390 proof already exist; OS ignores resize on the automation tab's hidden Space)
  - claim: Final live-quote paint on production
    what_would_verify: any human view of canada_stocks.html during TSX hours (quotes.json fresh, 12 targets in moved DOM, tick gated on document.hidden)
unresolved:
  - "HK V3.7 follower wave: released but not implemented — census first, per research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md"
  - "/api/regwall/check intermittent 503s (auth backend availability) — pre-existing, worth its own lane; loader retry (#6409, merged) mitigates"
next_actions:
  - "HK feature-disposition census against current HK producers/state (hk.html.j2 mode=stocks owners; Featured cohort owner; live-plane existence question; Southbound/A-H current producers) — return only if a NEW architectural conflict exists"
  - "Implement hk-stock-v36.js-class V3.7 follower per the frozen architecture; review; merge; deploy; entitled production proof"
  - "Final Sol return with Canada+HK receipts and reconciled regional feature ledger"
do_not_redo:
  - "Do not re-prove the V3.6 matrix — superseded (DEC:V37-SUPERSEDES-V36-ACCEPTANCE)"
  - "Do not re-run the V3.6/V3.7 design archaeology — no masterplan doc exists; authority = the three committed SOL_* packets + PR #6315/#6327/#6416 bodies"
  - "Do not re-add the days-in-state chip to the modal band — producer value is a forward wait-window (engine/cycles.py 'due in ~N trading days'), removed on adversarial review"
  - "Do not make canada-stock-v36.js (or a future hk sibling) anonymously public — the 401 boundary is the reviewed product"
  - "Do not fabricate a Canada 'Signal History →' destination — none exists; the trd dialog IS the integrated history (INTEGRATE_COMPRESS)"
  - "Do not implement the China follower architecture in this carrier (operator 2026-08-25)"
danger_areas:
  - "A pull_request run's merge ref is FROZEN at run creation: rerunning failed jobs after a main-side heal re-tests the OLD main — use update-branch (or a new push) to mint a fresh merge ref"
  - "gh pr checks --watch exits when currently-reported checks conclude — ci.yml packs that have not yet scheduled are invisible to it; verify the ci.yml run exists by branch before trusting a 'concluded' watch"
  - "Background shells die ~10 min in this harness (exit 144) — pace CI waits as chained sleep+single-check tasks, never one long watcher"
  - "The ZH stance-hue inversion on lane headers/chips is the site-wide Asia action-color convention, mirrored from the owner board — do not 'fix' it; only price-change chips carry the Western pin on Canada"
  - "Agent OS handoffs committed straight to main without validate break ci-pack-9 FLEET-WIDE (self-mod-fence agent-os step) — always run python3 scripts/agentos.py validate before pushing records"
---

# V3.7 Canada wave — closeout

Capability delta: entitled Canada visitors now get the full V3.7 journey —
truthful Top Picks projection, real Grid XOR Table, StockTable workbench,
restored Track Record (Evidence & Record) with real ledger + Methodology,
owner-native group-action intelligence inside Expand Leadership, and a
population mode that leadership filters can never silently change. Before:
V3.6 surface with Track Record deleted, invented lane vocabulary, and (per
Chairman review) population/XOR defects.

Continuation: the HK V3.7 follower wave is released and next — census first.
