---
workstream: WS:PROPHET-HK-CA-REVAMP
session: worktree-stock-dashboard-v3-6-rollout-d6f401 (Fable COO, V3.7 carrier — HK closeout)
model: fable
ended_because: complete
prs: [6433, 6429, 6416]
decisions:
  - DEC:V37-SUPERSEDES-V36-ACCEPTANCE
mission: >
  Complete the regional V3.7 rollout by carrying the HK follower from
  census through implementation, adversarial review, merge, deployment,
  and real production browser proof under the frozen
  SOL_HK_V37_FOLLOWER_ARCHITECTURE, then reconcile the regional ledger.
state_before: >
  Canada V3.7 was PROVEN_LIVE (2026-08-25, records merged via #6429). The HK
  wave was released, census-first: HK census established the Featured cohort
  owner (featured flag + stage=='live' → pv-featured), the definitive
  absence of a per-ticker HK live quote plane, verbatim Act-Now lane labels
  (same anv2 family as Canada), the sector-rotation table as the rank owner,
  the .sbah-* Mainland Money cards, and the HK trd wrapper
  (factordata/hk_track_ledger.json).
changed:
  - path: site/hk-stock-v36.js
    what: >
      New entitled HK V3.7 composer (PR #6433, merged cbf615eaa893):
      Featured-cohort Top Picks, zero fetches, no LIVE treatment, sector-only
      Leadership joining lanes + rotation rank/cycle-state, Southbound
      sig-*-gated Leading-Now cue + modal subband, Evidence & Record moving
      the HK trd chip/dialog, one-at-a-time disclosure toggles for four owner
      panels, Sol-gate population law, sm-hidden rescue rule.
  - path: templates/dashboard-icons.js
    what: HK loader block (bounded retry, own guard flag), byte-paired with site/dashboard-icons.js.
  - path: tests/test_hk_v37_composer.py
    what: >
      Discriminating pins incl. cross-file lane-label consistency vs
      templates/hk.html.j2, pv-featured + no-slice, no-LIVE + zero-fetch
      invariants, sm-hidden rescue, activate() population law — 8/8
      in-memory mutations killed; wired into legacy-jobs.yml.
  - path: research/STOCK_DASHBOARD_V37_HK_ACCEPTANCE_2026-08-26.md
    what: HK PROVEN_LIVE acceptance record (this PR) with the full production matrix and §13 fixture coverage.
verified:
  - claim: HK V3.7 merged as the exact reviewed head and CI-green
    command: gh pr view 6433 --json headRefOid,mergeCommit + gh run view 32920264252
    result: reviewed head 3a1487fd75a0 merged cbf615eaa893; ci.yml SUCCESS on that head; head re-read immediately before merge
  - claim: Production serves the HK composer through the real loader path
    command: "ssh VPS: grep dashboard-icons.js?v= site/hk_stocks.html; entitled browser: window.__mmHKStockV36 + body.hk-v37-mounted after plain reload"
    result: covering render re-stamped ?v=010b4a01 (built 2026-08-26 03:01 UTC); composer mounted on the entitled production journey with zero console errors
  - claim: Entitlement boundary intact
    command: "in-page fetch /hk-stock-v36.js?v=20260825 with credentials same-origin vs omit"
    result: entitled 200 private,no-store with V3.7 body; anonymous 401
  - claim: No-LIVE and Featured-cohort laws hold on production
    command: "entitled browser probes (see acceptance record)"
    result: zero LIVE text; Board chip = owner as_of; Top Picks = exactly the 3 pv-featured of 10; counter truthful
  - claim: Review BLOCKER repair effective under production conditions
    command: "entitled browser: dispatch resize events x3 under All Candidates; count visible cards + sm-hidden re-adds"
    result: theme.js re-added sm-hidden to 2 moved cards; all 10 remained visible (rescue rule wins)
  - claim: Sol-gate population law end-to-end
    command: "entitled browser: activate Internet & Tech under Top Picks; click .hk-v37-empty-switch"
    result: population stayed top; exact zero-state + invitation; deliberate switch revealed exactly 0268.HK
unverified:
  - claim: Exact-390px production pixel pass
    what_would_verify: any human view or resizable window at 390px on production (builder verified the exact bytes at 390 in a local real browser; OS ignores resize on the automation tab's hidden Space)
  - claim: "§13 fixtures 2 (Featured + wait-state) and 7 (A/H missing) under live data"
    what_would_verify: a future nightly whose board carries those states; behavior is code-guarded and test-covered meanwhile
unresolved:
  - "Cross-market nonblocking residue: composer modals (Canada + HK) have role=dialog without focus trapping — operable (Escape/Tab-order/Enter) but not conformant; design-system-level fix, both markets at once"
  - "/api/regwall/check intermittent 503s (auth backend) — pre-existing; bounded loader retry mitigates on both markets"
next_actions:
  - "Return to Sol: SUCCESS — Canada V3.7 + HK V3.7 both PROVEN_LIVE with receipts; regional grammar final (this handoff + the two acceptance records + the three SOL_* packets are the reconciled ledger)"
  - "US wave remains decoupled and unauthorized (V4 chain B1→B2/B3→B4 + reconciled Cell H prerequisites unchanged)"
do_not_redo:
  - "Do not add LIVE treatment to HK until a canonical per-ticker HK live quote plane exists AND is separately proven (then Asia up-red/down-green applies)"
  - "Do not replace the Featured cohort with positional Top Picks on HK (owner emits the selection; no-slice is test-pinned)"
  - "Do not weaken the sig-neu suppression of the Leading-Now flow cue — the owner's marker IS the materiality verdict"
  - "Do not remove the .sm-hidden rescue rules on either market — theme.js show-more holds live references to moved cards (test-pinned both markets)"
  - "Do not restore Fast Movers/Washout/Mainland Money/Screener as permanent panels — disclosure toggles are the INTEGRATE_COMPRESS home"
  - "Do not implement the China follower in this carrier; do not start US redesign code"
danger_areas:
  - "dashboard-icons.js is edge-immutable per URL: loader changes are INVISIBLE on production until a covering render re-stamps ?v= — a render running at merge time that started PRE-merge may still cover you only if it checks out latest main; verify the re-stamp on the VPS page bytes, never assume"
  - "theme.js show-more: any future composer that moves .pvcard nodes MUST ship a scoped .sm-hidden neutralizer or cards vanish on resize"
  - "The HK stocks page has no page-scoped body class; the composer's panel hide uses a descendant selector — blast radius was enumerated (9 .panel elements, all intended); re-enumerate if page structure changes"
  - "CDP javascript_tool calls >40s can time out on heavy pages — batch probes in small pieces"
---

# V3.7 HK follower — closeout

Capability delta: entitled HK visitors now get the full V3.7 journey —
Featured-cohort Top Picks that genuinely control the population, Grid XOR
Table over one population, sector leadership with owner rank + native
stances + cycle states, compressed group-action and Southbound intelligence
inside Expand Leadership, restored Track Record with Methodology, and
specialist desks on deliberate disclosure — with zero fabricated liveness.
Before: the legacy multi-shelf board; no composed journey; V3.6's HK wave
had produced no code.

The Canada→HK regional V3.7 rollout is COMPLETE. Final state: both markets
PROVEN_LIVE with dated acceptance records; regional grammar reconciled; US
decoupled; China out of carrier.
