---
workstream: "WS:MARKET-OS"
session: claude/marketontology-macro-command-p1-20260906
model: fable
ended_because: ci_handoff
mission: >
  One-dashboard consolidation of the fourteen macro_* workspaces plus the #6873 hub
  into site/macro_monetary.html under the frozen Macro Command spec
  research/market_intelligence_productization/MARKET_ONTOLOGY_F01_MACRO_COMMAND_DASHBOARD_SPEC_2026-09-06.md
  (PR #6914). Packets P1..P5 per spec §9; held F01 Wave-2 UI packets re-sliced as
  follow-on: A-F01-W2-1 (credit axis, MO-DELTA-008/MO-DELTA-013) → P6 credit sub-tab
  depth; A-F01-W2-5 (rates command-center depth, MO-PAID-002/MO-DELTA-012/MO-PAID-001)
  → P7 rates section depth; A-F01-W2-3 (transmission chains + indicators catalog,
  MO-PAID-005/MO-DELTA-010) → P8 Macro Command reference sections/deep links;
  A-F01-W2-4 (briefing vertical, MO-PAID-009/MO-PAID-011) → P9 Overview brief strip
  + AM edition. This handoff covers P1-B (copy guard + CI wiring).
state_before: >
  Fourteen macro_* workspace pages plus the #6873 hub live as separate routes under
  the shared suite shell; no FRONT-END CLARITY copy guard; no Macro Command shell
  CSS/JS packet on main.
changed:
  - path: scripts/check_macro_command_copy.py
    what: "New FRONT-END CLARITY copy guard — scans <main>+<title> visible text; §5 banned list + labels.py closed-vocab tokens + G2b bare timestamps; exempts .mc-details/.mc-primer."
  - path: tests/test_macro_command_copy_law.py
    what: "Fixture coverage for every banned family, exemptions, G2b as-of forms, annotation line-start, --selftest, and xfail live-hub assertion until P1-A lands."
  - path: .github/ci/legacy-jobs.yml
    what: "Extended market-os-macro-suite-pages paths + pytest run line with both P1 test files; added build + check_macro_command_copy.py steps."
  - path: agentos/handoffs/MARKET-ONTOLOGY-MACRO-COMMAND-2026-09-06.md
    what: "This P1 handoff record (P1-A shell files named in changed inventory; verified only for P1-B commands)."
  - path: templates/macro_command.css
    what: "P1-A owned — Macro Command tokens / shell layout (paired plain-copy)."
  - path: templates/macro_command.js
    what: "P1-A owned — rail routing / focus / sub-tab keyboard model."
  - path: templates/_macro_command_macros.html.j2
    what: "P1-A owned — nulled() and shared macros."
  - path: templates/macro_monetary.html.j2
    what: "P1-A owned — rail, .mc-shell grid, panel stubs, analyst control."
  - path: scripts/build_macro_suite_pages.py
    what: "P1-A owned — SECTIONS constant + SHARED_ASSETS for macro_command.* pairs."
  - path: site/macro_command.css
    what: "P1-A owned — plain-copy pair of templates/macro_command.css."
  - path: site/macro_command.js
    what: "P1-A owned — plain-copy pair of templates/macro_command.js."
  - path: tests/test_macro_command_shell.py
    what: "P1-A owned — shell/rail/routing/no-runtime-style assertions; named in CI only by P1-B."
verified:
  - claim: "Copy guard --selftest exits 0."
    command: "python3 scripts/check_macro_command_copy.py --selftest"
    result: "PASS — macro-command-copy: selftest OK"
  - claim: "Copy-law + annotation tests green (live hub xfail expected)."
    command: "python3 -m pytest tests/test_macro_command_copy_law.py tests/test_gh_annotation_line_start.py -q"
    result: "PASS — 13 passed, 1 xfailed"
  - claim: "closed_vocab_tokens enumerates labels.py machine ids."
    command: "python3 -c \"from scripts.check_macro_command_copy import closed_vocab_tokens; print(len(closed_vocab_tokens()))\""
    result: "PASS — 65 tokens (excludes 2-letter region codes)"
  - claim: "agentos handoff schema validates."
    command: "python3 scripts/agentos.py validate"
    result: "PASS — 0 error(s), 56 warning(s) (pre-existing phantoms/overdues)"
  - claim: "CI contract delta introduces 0 unnamed tests."
    command: "python3 scripts/check_contract_delta.py --base origin/main"
    result: "PASS — contract-delta: 0 introduced, 0 inherited"
  - claim: "ci-pack validate-only passes for pack 0."
    command: "python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 0 --pack-count 12 --validate-only"
    result: "PASS — Validated 209 legacy jobs; pack 0 selected"
unverified:
  - claim: "P1-A Macro Command shell (rail, tokens, macros, hub template, SHARED_ASSETS, paired site assets) builds and routes."
    what_would_verify: "pytest tests/test_macro_command_shell.py -q after P1-A lands; visual keyboard rail in both themes."
  - claim: "Live site/macro_monetary.html is copy-guard green."
    what_would_verify: "Remove xfail on test_live_hub_page_is_clean after P1-A merge; python3 scripts/check_macro_command_copy.py site/macro_monetary.html exits 0."
  - claim: "Paired plain-copy macro_command.css/js byte-match."
    what_would_verify: "python -m scripts.check_template_site_sync --fix on a full checkout with P1-A assets present."
unresolved:
  - "No agentos/workstreams/WS-MARKET-ONTOLOGY-F01-MACRO-MARKETS.md exists; this handoff binds to WS:MARKET-OS (closest existing F01/Market Ontology home)."
  - "git push over HTTPS rejected this host's gh OAuth token (invalid credentials) despite API admin; remote head update may use Contents/Git Data API."
next_actions:
  - "P2 — Command header: The Read + state strip (lib/macro_suite_labels.py PREDICATE_FORM/STATE_TONE, lib/macro_suite_view.py build_hub_view, templates/macro_monetary.html.j2 header, macro_command.css read/strip/chip, tests/test_macro_command_read.py)."
  - "P3 — Panel contract + Overview + first five sections (_macro_suite_shell macros, fragments, PRIMERS/CAPTIONS/STANCES, DEC-MACRO-COMMAND-STANCE-IS-GUIDANCE, tests/test_macro_command_panels.py)."
  - "P4 — Remaining six sections, sub-tabs, empty states, deep-link banner (labels copy, _macro_suite_nav banner, empty/subtab CSS, tests/test_macro_command_empty_states.py)."
  - "P5 — Copy-law sweep of shell, analyst polish, evidence (_macro_suite_shell §5 relocations, footer rewrite, analyst wiring, extend copy_law to fourteen pages)."
  - "After P1-A+P1-B merge: flip test_live_hub_page_is_clean from xfail to hard assert."
do_not_redo:
  - "No fused composite / regime chip (DNR:KILL-FUSED-COMPOSITE, DNR:KILL-REGIME-SCORECARD)."
  - "Do not redirect the 14 deep-link pages — keep and link into Macro Command."
  - "No chip tone from freshness (judge D1)."
  - "No chat.html?topic= parameter (D6)."
  - "No third global header; no templates/theme.css edits; no runtime style injection."
  - "No E1 copy for a section whose source has published (orchestrator ruling R3)."
danger_areas:
  - ".github/ci/legacy-jobs.yml pack rebalancing — exclusive-scope path list must name every new file or the job will not fire / contract-delta will fail."
  - "Paired plain-copy assets must byte-match (macro_command.css/js)."
  - "git add -A in a full worktree can commit data/ churn — add explicit paths only."
  - "The em-dash-without-.mq-sr scan is page-wide (P1-A / later packets)."
prs: [6873, 6914]
---

# MARKET-ONTOLOGY — Macro Command P1 handoff (2026-09-06)

P1 splits across two workers. **P1-B** (this session) owns the FRONT-END CLARITY
copy guard, its fixture tests, CI wiring for both P1 test files, and this
handoff. **P1-A** owns the shell CSS/JS/macros/hub template/builder/SHARED_ASSETS
and `tests/test_macro_command_shell.py`.

Workstream key used: `WS:MARKET-OS` — there is no
`WS:MARKET-ONTOLOGY-F01-MACRO-MARKETS` record under `agentos/workstreams/`.
