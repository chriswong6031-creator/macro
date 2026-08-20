---
workstream: "WS:INTRADAY-FLOW-P0-RECOVERY"
session: claude/intraday-flow-p0-recovery
model: opus
ended_because: context_budget
mission: >
  P0 restore Intraday Flow so production always paints the static board or a truthful
  degraded state; then correct the OPEX calendar clamp; then verdict the live
  Theta/M1/R2 plane without re-arming launchd.
state_before: >
  Production https://www.mastermind-x.com/intraday_flow.html frozen on "Reading the
  tape…" / "Loading leaders…" during RTH. origin/main at recon start
  dc12285c324684ac22b04abe0b712f323d46a72d. Live-flow meta.asof already stale
  (2026-08-12). OPEX engine labeling Aug. 19 as 0d / quad.
changed:
  - path: templates/intraday_flow.html.j2
    what: >
      quotePx helper; pin-watch requires finite price; computeAll rejects non-objects;
      polling registered before render(); fetch status from board coverage; bilingual
      BASE/quotes/tape/options stamp. Shipped in PR #6014.
  - path: site/intraday_flow.html
    what: Matching JS lockstep with the template. Shipped in PR #6014.
  - path: tests/test_intraday_flow_ncp_js.py
    what: >
      Boot regressions (empty RTH no-throw, L5 unknown, quotePx null, pin-path
      take_profits when price is on the wall). Shipped in PR #6014.
  - path: agentos/workstreams/WS-INTRADAY-FLOW-P0-RECOVERY.md
    what: New workstream for the remaining OPEX + live-flow waves.
  - path: agentos/discoveries/DSC-INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT.md
    what: Durable crash mechanism so a blank desk is not misread as Theta-down.
  - path: agentos/discoveries/DSC-OPEX-FUTURE-MONTH-LAST-OBS-CLAMP.md
    what: Durable calendar overwrite mechanism for PR-2.
verified:
  - claim: PR #6014 is MERGED and its squash is on origin/main
    command: "gh pr view 6014 --json state,mergedAt,mergeCommit; git fetch origin; git merge-base --is-ancestor d5de4e62779436f1551ce177b7506ffe468e2884 origin/main"
    result: "state MERGED mergedAt 2026-08-19T22:12:19Z mergeCommit d5de4e62779436f1551ce177b7506ffe468e2884; ancestor check passed"
  - claim: production HTML currently contains quotePx, boardHasPrice, and startPolling before render
    command: "curl -sS -m 20 https://www.mastermind-x.com/intraday_flow.html | python3 -c 'import sys; h=sys.stdin.read(); print(len(h), \"quotePx\", \"function quotePx\" in h, \"boardHasPrice\", \"function boardHasPrice\" in h)'"
    result: "bytes 307884; quotePx True; boardHasPrice True; startPolling_before_render True (2026-08-20 session close)"
  - claim: live_flow meta.asof is still 2026-08-12T20:09:06Z (DEGRADED, not a frontend crash)
    command: "curl -sS -m 15 https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/live_flow/meta.json"
    result: "schema live_flow.meta/v2 asof 2026-08-12T20:09:06.992244Z built_at 2026-08-12T20:09:45.521589Z"
  - claim: engine/opex.py still clamps future third Fridays onto idx[-1] with last-write-wins
    command: "sed -n '41,54p' engine/opex.py; test -f tests/test_opex.py; echo exit:$?"
    result: "on_or_before = idx[idx <= fri]; rows[on_or_before[-1]] = (m in QUAD_MONTHS); tests/test_opex.py absent"
  - claim: PR-1 local regression suite was green before merge
    command: "python3 -m pytest tests/test_intraday_flow_ncp_js.py tests/test_intraday_flow_stance.py -q"
    result: "97 passed (2026-08-19, head 48816075f188 before squash)"
unverified:
  - claim: A real browser session on production during RTH paints 116 names, non-zero lane chips, Spotlight, and zero uncaught console errors
    what_would_verify: "Open https://www.mastermind-x.com/intraday_flow.html at 1440 and ~390px during 09:25–16:05 ET; screenshot + console; confirm placeholders are replaced"
  - claim: Authenticated live/quotes.json covers the 116 leaders
    what_would_verify: "Fetch live/quotes.json with a logged-in session and intersect keys with BASE_DATA.leaders"
  - claim: Current served site/vol/regime.json still prints td_to_opex=0 / is_quad_cycle=true for today
    what_would_verify: "Read the nightly-built site/vol/regime.json opex and opex_risk.window_phase after a full checkout; public /vol/regime.json on 2026-08-20 returned nulls for those keys and is not a substitute for the engine fixture"
unresolved:
  - "PR-2 not started: future OPEX months still clamp onto the last price date (DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP)."
  - "PR-3 not closed: live options-flow source clock is ~7 sessions stale; M1 poller disarmed; Theta port 25503 was closed on 2026-08-19 census."
  - "Post-merge production browser proof (desktop + mobile) was not captured."
next_actions:
  - "Fetch origin/main, ff-only, new worktree claude/intraday-flow-opex-calendar off origin/main. Do not reuse claude/intraday-flow-p0-recovery."
  - "Browser-prove https://www.mastermind-x.com/intraday_flow.html during RTH (names, lane counts, Spotlight, no console TypeError). If still frozen, the VPS 3-min pull may not have the merge SHA — check served HTML for function quotePx."
  - "PR-2: add tests/test_opex.py cases A–E (history ends 2026-08-19 must not be expiry/quad; no Sep/Dec clamp; holiday roll-back preserved; real Mar/Jun/Sep/Dec quad). Then fix engine/opex.py expiration_days + null-safe tag/snapshot. Do not edit generated regime JSON by hand."
  - "After PR-2 merge, regenerate via the normal vol/intraday-flow builders and confirm glance_en no longer says 0d/quad on a non-expiry day."
  - "PR-3: re-curl live_flow/meta.json; meta.asof is source truth. Verdict exactly one of PROVEN_LIVE | BUILT_NOT_PROVEN | DEGRADED | BROKEN. Do not load ops/launchd options units."
do_not_redo:
  - "jsdom/boot archaeology for TypeError quote.price — reproduced and fixed in PR #6014 (DSC:INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT)."
  - "In-memory OPEX Aug-19 overwrite reproduction — proven; implement the contract, do not re-derive the mechanism (DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP)."
  - "Re-arming com.mastermind.liveflow or any ops/launchd options unit (WS-ADVANCED-DATA-OPTIONS AD-9 / DISARMED BY DEFAULT)."
  - "New options engine, second R2 plane, stance redesign, weighted scores, or try/catch swallow of render()."
  - "Calling the blank-desk screenshot a Theta outage. R2 live_flow/* was HTTP 200 with stale asof; BASE_DATA was embedded with 116 leaders."
  - "Collapsing L5/flow-missing into false. Unknown stays null."
  - "Normalizing dealerOf() to {} — empty object would hide the honest 'no chain' panel."
danger_areas:
  - "site/intraday_flow.html is Jinja-rendered, not a plain-copy pair. Edit the .j2 and keep JS lockstep; tests/test_intraday_flow_ncp_js.py REGIONS do not cover fetchQuotes/boot order."
  - "A write into a sparse omitted site/ truncates the committed HTML. Opt in with python3 scripts/worktree_sparse.py add site (or full) before touching site/intraday_flow.html."
  - "Anonymous quotes.json omits the 116 leaders. Stamp 'quotes live' only when boardHasPrice() is true."
  - "engine/opex.py tag() currently allows td_since==0 and td_to==0 together; in_opex_week treats null td_to as zero if you are not careful."
  - "glance_en in opex_risk / flowtracker base is a user-facing leak of the corrupted window_phase. Fix the engine; do not special-case the string."
  - "fetchFlow Promise.all inner catches return null; status must not become live on three nulls."
prs: [6014]
discoveries:
  - "DSC:INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT"
  - "DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP"
---

## §0 State

PR-1 (boot crash) is merged and the production HTML contains the fix. The desk can
still look "quiet" or show dashes for live columns because quotes/pulse often do not
cover these 116 names and live flow is a week stale. That is degraded data, not a
repeat of the boot throw.

PR-2 (OPEX calendar) and PR-3 (live-flow source clocks) are not done.

## §1 What is left, in order

1. Production browser proof of Intraday Flow during RTH.
2. PR-2 `engine/opex.py` + new `tests/test_opex.py` (cases A–E frozen in the 2026-08-19 recon).
3. PR-3 source-clock verdict only; no speculative poller re-arm.

## §2 What will bite the next session

- Reusing `claude/intraday-flow-p0-recovery` after squash-merge.
- Sparse worktree truncating `site/intraday_flow.html`.
- Fixing OPEX by editing `site/vol/regime.json` instead of the engine.
- Marking options `live` because R2 returns 200 with Aug. 12 `asof`.
- `typeof null === 'object'` if anyone "simplifies" computeAll to `typeof x === 'object'` without the `x &&` guard.
