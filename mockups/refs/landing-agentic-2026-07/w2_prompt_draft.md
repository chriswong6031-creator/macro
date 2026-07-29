# W2 draft (finalize after W1 audit — insert audit findings + any token corrections)

WAVE 2 of the landing "Instrument-Grade" redesign — Proof bands: Terminal, Prophet belt, Rotations, Filings. Fully pinned spec; no invented design decisions.

Worktree: /Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/landing-page-redesign-17d9a8 (branch checked out; W1 foundation is already merged into the working tree — tokens/utilities/textures exist in landing.css; USE them, do not re-invent).

READ FIRST: mockups/refs/landing-agentic-2026-07/DIRECTION.md §0 gates, §5 anatomy, §6.2 (terminal) §6.3 (belt) §6.4 (rotations+filings), §7 motion, §9 contracts. Refs: src/attio-03/05/07.png (band proportions, vignette scale), src/ours-en-01/02.png (before). W1 shots in shots/w1/ show the foundation in place.

SCOPE:
- #f-terminal (index.html ~292-440 + its CSS ~371-497): §6.2 environment (arcs texture, frame stroke rgba(255,255,255,.09), --r-xl, --sh-stage, blue under-glow), headline stays plain white (operator ruling: no two-tone), logo row normalization, .mk rail labels via existing classes. JS chart draw untouched.
- #f-prophet (~442-468 + CSS ~498-583): §6.3 — .tx-paper band, section hairline borders, float-tier cards, .mk receipts, designed delayed-winners chip (same words), edge-fade mask on crop. phDrift 95s + 640px mobile speed + .psc-stages aria UNTOUCHED (tests pin them).
- #f-rotations (~471-497) + #f-filings (~500-531) + shared .feature/.feat-grid CSS (~347-370, 584-622): §6.4 re-proportion (58/42, vignette min-height ~440px, band padding clamp(96px,11vw,148px), full-bleed hairline rules between bands), §5 card anatomy + receipt bars, tick bullets, h2s plain ink (operator ruling: no two-tone/gradient changes to headlines), .mk eyebrows. JS loops (TH lanes FLIP, POOL feed) untouched; only re-time entrance CSS to new easings.
- ZH parity on every touched string (data-zh twins, equally plain).
- Responsive: check every touched section at 390px (the 840/640 blocks in landing.css) — re-proportion must collapse gracefully (vignette stacks above copy).

CONTRACTS (reject-on-break): as W1 prompt §9 list — plus: do not touch hero/cover, pricing, AI, beyond, cband, footer; do not touch stamps; test set must stay green: python3 -m pytest tests/test_landing_navigation.py tests/test_public_chrome.py tests/test_onboard_compare_matrix.py tests/test_landing_pricing_cta.py tests/test_prophet_showcase.py tests/test_check_font_ui_defined.py tests/test_marketing_ad_plane_o.py tests/test_asset_stamp_lane_order.py -q

WORKFLOW: identical to W1 (edit templates/*, sync pairs, serve site/ on 8848, Playwright channel="chrome" sandbox-disabled, shots to shots/w2/ [1440 EN ?still per section + 1440 ZH + 390 EN + full-page], console clean, tests, self-critique vs refs, commit "landing W2: proof bands — terminal environment, belt paper, feature re-proportion", NO push/PR).

REPORT: files+delta, gates evidence, shot paths, deviations, notes for W3.


OPERATOR RULING 2026-07-29 (binding): hero copy block (3-line gradient h1 + dark LIVE pill + original sub) is FROZEN — do not touch. Section headlines stay plain ink; no two-tone, no gradients beyond the existing hero identity. .hd-mut is reserved/unused.
