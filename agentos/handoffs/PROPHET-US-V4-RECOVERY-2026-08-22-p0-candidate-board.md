---
workstream: WS:PROPHET-US-V4-RECOVERY
session: claude/p0-prophet-candidate-board
model: fable
ended_because: complete
mission: >
  Chairman/Sol P0 interruption (GitHub #6185, Linear MAS-111): restore the full
  current `us_standouts.buy` candidate population as the immediately useful
  principal Prophet experience on /us_stocks.html, behind a Candidates|Plans
  source toggle with Candidates default, without merging the two record kinds
  and without absorbing P-LAB-UI or P-MP1-DENSE.
state_before: >
  PR #6076 (P-MP1-SHELL) re-sourced the principal Setups grid from the candidate
  screener to the plan book and deleted the rich candidate card grid. On the live
  page the candidate population was reachable only as three `.cand-row` text rows
  plus five shelf pills — ZERO candidate cards rendered. Three different numbers
  described that one population on one screen (heading 72, gate note 60, subtitle
  "60 shown · 76 setups"), and the heading printed the literal characters
  `<b>72</b>` because every `t()` in this repo escapes its argument.
changed:
  - path: templates/dashboard.html.j2
    what: >
      `data-prophet-src` on #us-standouts (candidates when the candidate board
      loaded, else plans); unconditional #us-src-toggle reusing the existing
      .st-view-toggle primitive; CSS showing exactly one population and hiding
      the Grid/Table toggle in Plans mode; #us-plan-block wrapper around the
      ladder/plan grid/plan wall; restored #us-cand-grid including
      _us_board_cards.html.j2; restored #us-tier-wall keyed on `gate`; typed
      Candidates-unavailable .mx-empty state; census now quotes gate.total with
      a residual "Other" shelf; three escaped-`<b>` sites rewritten as explicit
      bilingual twins; mixed-unit board subtitle clause deleted; hydrate() now
      consumes payload.cards_html through mergeBoardCards; teardown removes
      #us-tier-wall; the W-L1 provisional path saves/restores the new toggle.
  - path: templates/_us_board_cards.html.j2
    what: data-sm-heading="1" on .nb-stage-hd and .nb-lane-hd — nothing else.
  - path: templates/theme.js
    what: >
      initShowMore counts RECORDS for its display count and both button labels
      (recTotal/recShown/nextRecs, heading-excluding) while paging arithmetic
      stays in grid-child units. Grids without headings are unaffected.
  - path: site/theme.js
    what: paired plain-copy asset, byte-synced to templates/theme.js.
  - path: tests/test_p0_prophet_candidate_board.py
    what: new suite, 16 tests pinning the toggle, both grids' separation, the tier boundary, the census arithmetic, the escaped-`<b>` regression, and the hydration contract.
  - path: tests/test_p_mp1_shell_repair_round.py
    what: N3 teardown test extended to assert BOTH #us-tier-wall and #us-life-wall are targeted.
  - path: .github/ci/legacy-jobs.yml
    what: "one line appended to the EXISTING `run:` step that already names test_p_mp1_shell_repair_round.py — no new job."
  - path: agentos/decisions/DEC-P0-PROPHET-CANDIDATE-BOARD-RESTORE.md
    what: new decision record for the presentation-law amendment.
  - path: research/migration_packets/MP-1-prophet-board.md
    what: Amendment 2 — the two-source presentation law, and the answer that P-MP1-DENSE builds its dense Table for PLANS ONLY.
verified:
  - claim: "The candidate producer is alive and its locked remainder has been shipping and being discarded since #6076."
    command: "ssh root@146.190.142.17 'python3 -c ...' on /opt/macro/site/premiumdata/us_stocks.json at production HEAD da336ec61f8"
    result: "gated=True total=60 preview=3 locked=57; cards_html 326,143 bytes with 57 cards and 5 nb-stage-hd headings; rows=57 with 57 distinct tickers. `grep -n '\\.cards_html\\b' templates/dashboard.html.j2` on origin/main returned zero call sites."
  - claim: "The live page renders zero candidate cards; the three pvcard elements it does have are PLAN cards."
    command: "curl -s https://www.mastermind-x.com/us_stocks.html > live.html; python3 -c 'count pvcard, locate each'"
    result: "4 matches: 3 inside #us-life-grid, the 4th inside a JS string in _pvcPaint. Zero candidate cards."
  - claim: "The escaped-<b> and mixed-unit defects are live, not theoretical."
    command: "playwright against https://www.mastermind-x.com/us_stocks.html, reading document.body.innerText and #us-board-sub"
    result: "escapedB=2 occurrences of the literal `<b>NN</b>`; mx-sec-total innerText `<b>72</b> screened tonight`; #us-board-sub `60 shown · 76 setups · green dot = ...`."
  - claim: "The four suites that govern this surface pass on the PR head."
    command: "python3 -m pytest tests/test_p0_prophet_candidate_board.py tests/test_p_mp1_shell_repair_round.py tests/test_wl1_lifecycle_neutralization.py tests/test_public_chrome.py -q"
    result: "58 passed, 3 warnings in 44.22s (run by the commissioning session, not only the builder)."
  - claim: "The paired plain-copy asset is byte-synced."
    command: "python3 -m scripts.check_template_site_sync"
    result: "template<->site sync OK (91 pairs checked), exit 0."
  - claim: "scripts/build_site.py needed no change."
    command: "git diff --stat 2c752170fa75..HEAD -- scripts/build_site.py"
    result: "empty."
  - claim: "The AgentOS store is clean with the new decision record."
    command: "python3 scripts/agentos.py validate"
    result: "520 records (168 decisions) — 0 errors, 22 pre-existing review-overdue warnings."
unverified:
  - claim: "An entitled production session sees the full 60-candidate board after hydration."
    what_would_verify: "A real signed-in entitled session on the deployed page. The commissioning session proves the same path by fulfilling the premium payload request with the REAL production bytes from the VPS, which exercises the real fetch -> hydrate -> mergeBoardCards chain but not Caddy's auth decision (untouched by this PR, and currently returning 401 anonymous as designed)."
  - claim: "A real intraday tick repaints a candidate card."
    what_would_verify: "A weekday session. 2026-08-22 is a Saturday and live/quotes.json serves a Friday-close snapshot (delayMin ~1189), so the proof intercepts the real quotes feed with one candidate's price perturbed and shows that candidate repainting while no plan card moves — real production live.js, synthetic upstream price."
unresolved:
  - "The candidate tier wall now sits ABOVE the 'carries no plan yet' sample, so a little candidate text remains below the paywall. Both are capped at preview_rows, so nothing leaks; knowingly retained for the smallest reversible diff."
  - "The plan wall's own #us-life-signin is still revealed by nothing. Restoring #us-tw-signin fixes the sign-in offer for Candidates mode only."
next_actions:
  - "Merge PR #6243 on concluded-green checks, then watch the shared render.yml run (dashboard.html.j2 maps to region `macro`) to conclusion."
  - "Run the production proof harness in the session scratchpad (verify_p0.py, live_repaint_proof.py) against the deployed page and record the deployed SHA."
  - "Return to Sol for review before resuming P-LAB-UI / P-MP1-DENSE sequencing, per #6185's stop condition."
  - "Resume the Day-6/B1 cutover at its existing checkpoint: the MACRO-PRIVATE-CUTOVER READY receipt is delivered and the Chairman's visibility flip is still the next act there. This P0 changed nothing about it."
do_not_redo:
  - "Do not re-derive whether the candidate producer is alive. It is. The real production premium payload at production HEAD da336ec61f8 carries the full locked remainder (cards_html 326,143 bytes / 57 cards / 5 stage headings, plus 57 flat rows) and has been shipped and discarded on every entitled session since #6076 because hydrate() never read `cards_html`."
  - "Do not change scripts/build_site.py for this surface. _split_us_board, _us_board_group_items and _write_us_payload already produce everything the restored grid and its hydration need. This slice needed zero Python change."
  - "Do not touch the W-L1 selector `.nbgrid[data-showmore-rows]:not([data-provboard]):not([data-mp1-grid])` (templates/dashboard.html.j2). A candidate grid that simply omits data-mp1-grid is re-acquired by it automatically; tests/test_wl1_lifecycle_neutralization.py pins the string."
  - "Do not rewrite mergeBoardCards. It was dead code from before #6076, not broken code: it merges the payload's grouped cards into an existing grid, drops duplicate headings and preserves stage rank. It is called again now."
  - "Do not fold us_standouts.ran into the candidate census. It is a separate array with its own section (_us_ran_rows.html.j2) and its own tier gate (pgate.ran); folding it in is what made the heading and the gate note quote different denominators."
  - "Do not build a second dense candidate Table. USStockTable already renders the candidate population from the payload's flat rows. P-MP1-DENSE owes the PLAN half only — recorded in MP-1 Amendment 2."
  - "Do not blame engine/i18n.py for an escaped-<b> defect in a template that defines its own t() macro. scripts/build_site.py registers td/tr/t_pctile but NOT t, so dashboard.html.j2 uses the local macro at its line 14. Both implementations escape the argument, so the FIX is the same either way — but the citation is not."
danger_areas:
  - "Every t()/td() here escapes its argument — 147 templates define a local Jinja macro whose {{ en }} escapes under autoescape=True, and engine/i18n.py:34 uses Markup.format which escapes too. HTML composed into the argument renders as visible tags, and |safe seals it rather than fixing it. Pin regressions on the RENDERED html ('&lt;b&gt;' not in html), never on template source."
  - "initShowMore (templates/theme.js) is idempotent per element via data-smInit and closes over the children it saw at first init. Appending into an initialised grid leaves its show-more bar permanently stale — always swap in a FRESH element and re-run it."
  - "initShowMore counts grid CHILDREN, and _us_board_cards.html.j2 emits stage headings as children. Any grid with headings needs the data-sm-heading exclusion or its 'Showing X of Y' states a number no record kind on the page has."
  - "A grid that initialises while display:none measures one column. theme.js's ResizeObserver already re-resolves it when it becomes visible — do not add a second re-init mechanism."
  - "The anonymous document now carries BOTH populations' previews (3 candidate + 3 plan) rather than one. Each respects its own unchanged server gate, and candidate previews are not plan data, so the B1 §8b boundary is untouched. Do not widen either preview to make a layout look fuller."
  - "data-prophet-src is baked as `plans` when the candidate board is absent. Gating the source toggle on the same condition makes the typed Candidates-unavailable state permanently unreachable — that defect was written into the first spec and caught in review. The toggle renders unconditionally for that reason."
prs: [6243]
decisions:
  - "DEC:P0-PROPHET-CANDIDATE-BOARD-RESTORE"
---

Continuation note for whoever picks this up: #6185's stop condition is "stop after
this P0 is live" and return to Sol before resuming P-LAB-UI / P-MP1-DENSE. The
Day-6/B1 cutover is paused at a clean checkpoint, not abandoned — its
`MACRO-PRIVATE-CUTOVER READY` receipt stands and the Chairman's repository
visibility flip is still the next act there.
